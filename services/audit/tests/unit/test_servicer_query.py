from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import ClassVar

import grpc
import pytest
from sqlalchemy.exc import OperationalError

from app.core.pseudonym import PseudonymKeyError
from app.server import servicer as servicer_module
from app.server.grpc_gen import audit_pb2, common_pb2
from tests.conftest import AbortError, FakeServicerContext

pytestmark = pytest.mark.unit


ACCESS_KIND = audit_pb2.AuditEvent.DESCRIPTOR.fields_by_name["audit_log_accessed"].number


@dataclass
class StoredRow:
    sequence_number: int
    chain_hash: bytes
    leaf_hash: bytes
    persisted_at: datetime
    event_bytes: bytes | None
    erased_at: datetime | None = None


class FakeSession:
    def __init__(self) -> None:
        self.committed = False

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, *exc_info) -> bool:
        return False

    async def commit(self) -> None:
        self.committed = True


class QueryRepository:
    rows: ClassVar[list[StoredRow]] = []
    query_calls: ClassVar[list[dict]] = []
    append_calls: ClassVar[list[dict]] = []
    query_error: Exception | None = None

    def __init__(self, session) -> None:
        self.session = session

    async def query(self, **kwargs) -> list[StoredRow]:
        QueryRepository.query_calls.append(kwargs)
        if QueryRepository.query_error is not None:
            raise QueryRepository.query_error
        return QueryRepository.rows

    async def append(self, **kwargs):
        QueryRepository.append_calls.append(kwargs)


def make_stored_event(actor: str = "actor-1") -> bytes:
    event = audit_pb2.AuditEvent(
        schema_version=1,
        event_id="11111111-1111-1111-1111-111111111111",
        source_service=common_pb2.SOURCE_SERVICE_AUTH,
        actor=actor,
        severity=common_pb2.SEVERITY_INFO,
    )
    event.occurred_at.FromDatetime(datetime.now(UTC))
    event.service_lifecycle.version = "0.1.0"
    return event.SerializeToString(deterministic=True)


def make_row(sequence_number: int = 1, **overrides) -> StoredRow:
    defaults = {
        "sequence_number": sequence_number,
        "chain_hash": bytes(range(32)),
        "leaf_hash": bytes(range(32, 64)),
        "persisted_at": datetime(2026, 8, 5, 12, 0, tzinfo=UTC),
        "event_bytes": make_stored_event(),
    }
    defaults.update(overrides)
    return StoredRow(**defaults)


@pytest.fixture
def repository(monkeypatch: pytest.MonkeyPatch):
    QueryRepository.rows = []
    QueryRepository.query_calls = []
    QueryRepository.append_calls = []
    QueryRepository.query_error = None
    session = FakeSession()
    monkeypatch.setattr(servicer_module, "get_sessionmaker", lambda: lambda: session)
    monkeypatch.setattr(servicer_module, "AuditRepository", QueryRepository)
    QueryRepository.session = session
    return QueryRepository


async def test_an_empty_result_returns_no_events(repository, context: FakeServicerContext) -> None:
    reply = await servicer_module.AuditServicer().QueryEvents(
        audit_pb2.QueryEventsRequest(), context
    )
    assert list(reply.events) == []
    assert reply.next_page_token == ""


async def test_a_stored_event_is_returned_with_its_position(
    repository, context: FakeServicerContext
) -> None:
    repository.rows = [make_row(sequence_number=4)]
    reply = await servicer_module.AuditServicer().QueryEvents(
        audit_pb2.QueryEventsRequest(), context
    )
    assert reply.events[0].sequence_number == "4"
    assert reply.events[0].chain_hash == bytes(range(32))
    assert reply.events[0].leaf_hash == bytes(range(32, 64))


async def test_the_stored_payload_is_parsed_back(repository, context: FakeServicerContext) -> None:
    repository.rows = [make_row()]
    reply = await servicer_module.AuditServicer().QueryEvents(
        audit_pb2.QueryEventsRequest(), context
    )
    assert reply.events[0].event.actor == "actor-1"
    assert reply.events[0].erased is False


async def test_an_erased_row_is_returned_as_a_tombstone(
    repository, context: FakeServicerContext
) -> None:
    erased_at = datetime(2026, 8, 6, 9, 0, tzinfo=UTC)
    repository.rows = [make_row(event_bytes=None, erased_at=erased_at)]
    reply = await servicer_module.AuditServicer().QueryEvents(
        audit_pb2.QueryEventsRequest(), context
    )
    entry = reply.events[0]
    assert entry.erased is True
    assert entry.HasField("event") is False
    assert entry.erased_at.ToDatetime(tzinfo=UTC) == erased_at


async def test_an_erased_row_keeps_its_chain_hashes(
    repository, context: FakeServicerContext
) -> None:
    repository.rows = [make_row(event_bytes=None, erased_at=datetime(2026, 8, 6, 9, 0, tzinfo=UTC))]
    reply = await servicer_module.AuditServicer().QueryEvents(
        audit_pb2.QueryEventsRequest(), context
    )
    assert reply.events[0].chain_hash == bytes(range(32))
    assert reply.events[0].leaf_hash == bytes(range(32, 64))


async def test_an_undecodable_payload_is_cleared_rather_than_raised(
    repository, context: FakeServicerContext
) -> None:
    repository.rows = [make_row(event_bytes=b"\xff\xff\xff\xff not protobuf")]
    reply = await servicer_module.AuditServicer().QueryEvents(
        audit_pb2.QueryEventsRequest(), context
    )
    assert reply.events[0].HasField("event") is False
    assert reply.events[0].sequence_number == "1"


async def test_the_default_page_size_is_applied(repository, context: FakeServicerContext) -> None:
    await servicer_module.AuditServicer().QueryEvents(audit_pb2.QueryEventsRequest(), context)
    assert repository.query_calls[0]["page_size"] == servicer_module._DEFAULT_PAGE_SIZE


async def test_a_requested_page_size_is_honoured(repository, context: FakeServicerContext) -> None:
    await servicer_module.AuditServicer().QueryEvents(
        audit_pb2.QueryEventsRequest(page_size=25), context
    )
    assert repository.query_calls[0]["page_size"] == 25


async def test_an_oversized_page_size_is_clamped(repository, context: FakeServicerContext) -> None:
    await servicer_module.AuditServicer().QueryEvents(
        audit_pb2.QueryEventsRequest(page_size=100000), context
    )
    assert repository.query_calls[0]["page_size"] == servicer_module._MAX_PAGE_SIZE


async def test_a_negative_page_size_falls_back_to_the_default(
    repository, context: FakeServicerContext
) -> None:
    await servicer_module.AuditServicer().QueryEvents(
        audit_pb2.QueryEventsRequest(page_size=-5), context
    )
    assert repository.query_calls[0]["page_size"] == servicer_module._DEFAULT_PAGE_SIZE


async def test_a_full_page_offers_a_continuation_token(
    repository, context: FakeServicerContext
) -> None:
    repository.rows = [make_row(sequence_number=index) for index in range(1, 4)]
    reply = await servicer_module.AuditServicer().QueryEvents(
        audit_pb2.QueryEventsRequest(page_size=3), context
    )
    assert reply.next_page_token == "3"


async def test_a_partial_page_ends_the_pagination(repository, context: FakeServicerContext) -> None:
    repository.rows = [make_row(sequence_number=1)]
    reply = await servicer_module.AuditServicer().QueryEvents(
        audit_pb2.QueryEventsRequest(page_size=3), context
    )
    assert reply.next_page_token == ""


async def test_a_page_token_resumes_after_the_given_position(
    repository, context: FakeServicerContext
) -> None:
    await servicer_module.AuditServicer().QueryEvents(
        audit_pb2.QueryEventsRequest(page_token="12"), context
    )
    assert repository.query_calls[0]["after_sequence_number"] == 12


async def test_an_absent_page_token_starts_at_the_beginning(
    repository, context: FakeServicerContext
) -> None:
    await servicer_module.AuditServicer().QueryEvents(audit_pb2.QueryEventsRequest(), context)
    assert repository.query_calls[0]["after_sequence_number"] is None


@pytest.mark.parametrize("token", ["abc", "-1", "1.5", "9999999999999999999999x"])
async def test_a_malformed_page_token_is_refused(
    repository, context: FakeServicerContext, token: str
) -> None:
    with pytest.raises(AbortError) as excinfo:
        await servicer_module.AuditServicer().QueryEvents(
            audit_pb2.QueryEventsRequest(page_token=token), context
        )
    assert excinfo.value.code == grpc.StatusCode.INVALID_ARGUMENT


async def test_the_time_window_is_passed_through(repository, context: FakeServicerContext) -> None:
    start = datetime(2026, 8, 1, tzinfo=UTC)
    end = datetime(2026, 8, 8, tzinfo=UTC)
    request = audit_pb2.QueryEventsRequest()
    request.from_time.FromDatetime(start)
    request.to_time.FromDatetime(end)
    await servicer_module.AuditServicer().QueryEvents(request, context)
    call = repository.query_calls[0]
    assert call["from_time"] == start
    assert call["to_time"] == end


async def test_the_filters_are_passed_through(repository, context: FakeServicerContext) -> None:
    request = audit_pb2.QueryEventsRequest(
        source_service=common_pb2.SOURCE_SERVICE_AUTH,
        actor="nizar",
        min_severity=common_pb2.SEVERITY_WARNING,
    )
    await servicer_module.AuditServicer().QueryEvents(request, context)
    call = repository.query_calls[0]
    assert call["source_service"] == common_pb2.SOURCE_SERVICE_AUTH
    assert call["actor"] == "nizar"
    assert call["min_severity"] == common_pb2.SEVERITY_WARNING


async def test_the_query_is_recorded_in_the_log(repository, context: FakeServicerContext) -> None:
    await servicer_module.AuditServicer().QueryEvents(audit_pb2.QueryEventsRequest(), context)
    assert len(repository.append_calls) == 1
    assert repository.append_calls[0]["payload_kind"] == ACCESS_KIND


async def test_the_access_record_is_attributed_to_the_audit_service(
    repository, context: FakeServicerContext
) -> None:
    await servicer_module.AuditServicer().QueryEvents(audit_pb2.QueryEventsRequest(), context)
    assert repository.append_calls[0]["source_service"] == common_pb2.SOURCE_SERVICE_AUDIT


async def test_the_access_record_counts_the_rows_returned(
    repository, context: FakeServicerContext
) -> None:
    repository.rows = [make_row(sequence_number=index) for index in range(1, 4)]
    await servicer_module.AuditServicer().QueryEvents(audit_pb2.QueryEventsRequest(), context)
    recorded = audit_pb2.AuditEvent()
    recorded.ParseFromString(repository.append_calls[0]["event_bytes"])
    assert recorded.audit_log_accessed.rows_returned == 3


async def test_the_access_record_names_the_events_scope(
    repository, context: FakeServicerContext
) -> None:
    await servicer_module.AuditServicer().QueryEvents(audit_pb2.QueryEventsRequest(), context)
    recorded = audit_pb2.AuditEvent()
    recorded.ParseFromString(repository.append_calls[0]["event_bytes"])
    assert recorded.audit_log_accessed.scope == audit_pb2.AUDIT_QUERY_SCOPE_EVENTS


async def test_the_access_record_pseudonymises_the_actor_filter(
    repository, context: FakeServicerContext
) -> None:
    await servicer_module.AuditServicer().QueryEvents(
        audit_pb2.QueryEventsRequest(actor="nizar"), context
    )
    recorded = audit_pb2.AuditEvent()
    recorded.ParseFromString(repository.append_calls[0]["event_bytes"])
    assert len(recorded.audit_log_accessed.filter_actor_hmac) == 32
    assert b"nizar" not in recorded.audit_log_accessed.filter_actor_hmac


async def test_the_access_record_omits_an_absent_actor_filter(
    repository, context: FakeServicerContext
) -> None:
    await servicer_module.AuditServicer().QueryEvents(audit_pb2.QueryEventsRequest(), context)
    recorded = audit_pb2.AuditEvent()
    recorded.ParseFromString(repository.append_calls[0]["event_bytes"])
    assert recorded.audit_log_accessed.filter_actor_hmac == b""


async def test_the_access_record_carries_the_time_window(
    repository, context: FakeServicerContext
) -> None:
    start = datetime(2026, 8, 1, tzinfo=UTC)
    request = audit_pb2.QueryEventsRequest()
    request.from_time.FromDatetime(start)
    await servicer_module.AuditServicer().QueryEvents(request, context)
    recorded = audit_pb2.AuditEvent()
    recorded.ParseFromString(repository.append_calls[0]["event_bytes"])
    assert recorded.audit_log_accessed.window_from.ToDatetime(tzinfo=UTC) == start


async def test_the_access_record_carries_a_fresh_event_id(
    repository, context: FakeServicerContext
) -> None:
    await servicer_module.AuditServicer().QueryEvents(audit_pb2.QueryEventsRequest(), context)
    await servicer_module.AuditServicer().QueryEvents(audit_pb2.QueryEventsRequest(), context)
    first = repository.append_calls[0]["event_id"]
    second = repository.append_calls[1]["event_id"]
    assert first != second


async def test_the_query_commits_only_once(repository, context: FakeServicerContext) -> None:
    await servicer_module.AuditServicer().QueryEvents(audit_pb2.QueryEventsRequest(), context)
    assert repository.session.committed is True


async def test_a_store_failure_aborts_as_unavailable(
    repository, context: FakeServicerContext
) -> None:
    repository.query_error = OperationalError("select", {}, Exception("connection lost"))
    with pytest.raises(AbortError) as excinfo:
        await servicer_module.AuditServicer().QueryEvents(audit_pb2.QueryEventsRequest(), context)
    assert excinfo.value.code == grpc.StatusCode.UNAVAILABLE


async def test_an_unrecordable_access_refuses_the_query(
    repository, context: FakeServicerContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(domain: str, value: str) -> bytes:
        raise PseudonymKeyError("pseudonym key file missing")

    monkeypatch.setattr(servicer_module, "pseudonymize", broken)
    with pytest.raises(AbortError) as excinfo:
        await servicer_module.AuditServicer().QueryEvents(
            audit_pb2.QueryEventsRequest(actor="nizar"), context
        )
    assert excinfo.value.code == grpc.StatusCode.FAILED_PRECONDITION


async def test_an_unrecordable_access_does_not_commit(
    repository, context: FakeServicerContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(domain: str, value: str) -> bytes:
        raise PseudonymKeyError("pseudonym key file missing")

    monkeypatch.setattr(servicer_module, "pseudonymize", broken)
    with pytest.raises(AbortError):
        await servicer_module.AuditServicer().QueryEvents(
            audit_pb2.QueryEventsRequest(actor="nizar"), context
        )
    assert repository.session.committed is False
