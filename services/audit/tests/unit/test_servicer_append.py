from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import grpc
import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.config import get_settings
from app.repositories.audit_repository import AppendResult
from app.server import servicer as servicer_module
from app.server.grpc_gen import audit_pb2, common_pb2
from app.server.interceptors import _PEER_SERVICE
from tests.conftest import AbortError, FakeServicerContext

pytestmark = pytest.mark.unit


class FakeSession:
    def __init__(self) -> None:
        self.committed = False

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, *exc_info) -> bool:
        return False

    async def commit(self) -> None:
        self.committed = True


class RecordingRepository:
    def __init__(self, session, result: AppendResult | None = None, error: Exception | None = None):
        self.session = session
        self.result = result
        self.error = error

    async def append(self, **kwargs) -> AppendResult:
        RecordingRepository.calls.append(kwargs)
        if RecordingRepository.error is not None:
            raise RecordingRepository.error
        return RecordingRepository.result


def _accepted_result() -> AppendResult:
    return AppendResult(
        sequence_number=7,
        leaf_hash=bytes(range(32)),
        chain_hash=bytes(range(32, 64)),
        persisted_at=datetime(2026, 8, 5, 12, 0, tzinfo=UTC),
        duplicate=False,
    )


@pytest.fixture
def repository(monkeypatch: pytest.MonkeyPatch):
    RecordingRepository.calls = []
    RecordingRepository.result = _accepted_result()
    RecordingRepository.error = None
    session = FakeSession()
    monkeypatch.setattr(servicer_module, "get_sessionmaker", lambda: lambda: session)
    monkeypatch.setattr(servicer_module, "AuditRepository", RecordingRepository)
    RecordingRepository.session = session
    return RecordingRepository


@pytest.fixture
def allow_rate(monkeypatch: pytest.MonkeyPatch):
    calls: list[int] = []

    async def check(source_service: int) -> bool:
        calls.append(source_service)
        return True

    monkeypatch.setattr(servicer_module, "check_append_rate", check)
    return calls


@pytest.fixture
def caller_is_auth():
    token = _PEER_SERVICE.set(common_pb2.SOURCE_SERVICE_AUTH)
    yield common_pb2.SOURCE_SERVICE_AUTH
    _PEER_SERVICE.reset(token)


def make_event(
    *,
    source_service: int = common_pb2.SOURCE_SERVICE_AUTH,
    event_id: str | None = None,
    schema_version: int = 1,
    occurred_at: datetime | None = None,
    with_payload: bool = True,
    actor: str = "actor-1",
    severity: int = common_pb2.SEVERITY_INFO,
    trace_id: str = "",
) -> audit_pb2.AuditEvent:
    event = audit_pb2.AuditEvent(
        schema_version=schema_version,
        event_id=event_id if event_id is not None else str(uuid.uuid4()),
        source_service=source_service,
        actor=actor,
        severity=severity,
        trace_id=trace_id,
    )
    event.occurred_at.FromDatetime(occurred_at or datetime.now(UTC))
    if with_payload:
        event.service_lifecycle.service = source_service
        event.service_lifecycle.event_kind = audit_pb2.LIFECYCLE_EVENT_KIND_STARTED
        event.service_lifecycle.version = "0.1.0"
    return event


async def test_accepted_append_reports_the_stored_position(
    repository, allow_rate, caller_is_auth, context: FakeServicerContext
) -> None:
    reply = await servicer_module.AuditServicer().AppendEvent(make_event(), context)
    assert reply.status == audit_pb2.APPEND_STATUS_ACCEPTED
    assert reply.sequence_number == "7"
    assert reply.chain_hash == bytes(range(32, 64))
    assert reply.leaf_hash == bytes(range(32))


async def test_accepted_append_commits(
    repository, allow_rate, caller_is_auth, context: FakeServicerContext
) -> None:
    await servicer_module.AuditServicer().AppendEvent(make_event(), context)
    assert repository.session.committed is True


async def test_stored_bytes_are_the_deterministic_serialisation(
    repository, allow_rate, caller_is_auth, context: FakeServicerContext
) -> None:
    event = make_event()
    await servicer_module.AuditServicer().AppendEvent(event, context)
    assert repository.calls[0]["event_bytes"] == event.SerializeToString(deterministic=True)


async def test_stored_fields_come_from_the_request(
    repository, allow_rate, caller_is_auth, context: FakeServicerContext
) -> None:
    event = make_event(actor="nizar", trace_id="a" * 32)
    await servicer_module.AuditServicer().AppendEvent(event, context)
    call = repository.calls[0]
    assert call["actor"] == "nizar"
    assert call["trace_id"] == "a" * 32
    assert call["event_id"] == event.event_id
    assert call["source_service"] == common_pb2.SOURCE_SERVICE_AUTH


async def test_payload_kind_is_recorded_from_the_oneof(
    repository, allow_rate, caller_is_auth, context: FakeServicerContext
) -> None:
    expected = audit_pb2.AuditEvent.DESCRIPTOR.fields_by_name["service_lifecycle"].number
    await servicer_module.AuditServicer().AppendEvent(make_event(), context)
    assert repository.calls[0]["payload_kind"] == expected


async def test_a_caller_cannot_claim_another_service(
    repository, allow_rate, caller_is_auth, context: FakeServicerContext
) -> None:
    event = make_event(source_service=common_pb2.SOURCE_SERVICE_API)
    reply = await servicer_module.AuditServicer().AppendEvent(event, context)
    assert reply.status == audit_pb2.APPEND_STATUS_REJECTED
    assert repository.calls == []


async def test_an_unidentified_caller_is_rejected(
    repository, allow_rate, context: FakeServicerContext
) -> None:
    event = make_event(source_service=common_pb2.SOURCE_SERVICE_AUTH)
    reply = await servicer_module.AuditServicer().AppendEvent(event, context)
    assert reply.status == audit_pb2.APPEND_STATUS_REJECTED
    assert repository.calls == []


async def test_an_unspecified_source_service_is_rejected(
    repository, allow_rate, caller_is_auth, context: FakeServicerContext
) -> None:
    event = make_event(source_service=common_pb2.SOURCE_SERVICE_UNSPECIFIED)
    reply = await servicer_module.AuditServicer().AppendEvent(event, context)
    assert reply.status == audit_pb2.APPEND_STATUS_REJECTED


@pytest.mark.parametrize(
    "event_id",
    ["", "not-a-uuid", "12345", "00000000-0000-0000-0000-00000000000", "  "],
)
async def test_a_malformed_event_id_is_rejected(
    repository, allow_rate, caller_is_auth, context: FakeServicerContext, event_id: str
) -> None:
    reply = await servicer_module.AuditServicer().AppendEvent(
        make_event(event_id=event_id), context
    )
    assert reply.status == audit_pb2.APPEND_STATUS_REJECTED
    assert repository.calls == []


async def test_an_absent_schema_version_falls_back_to_the_configured_one(
    repository, allow_rate, caller_is_auth, context: FakeServicerContext
) -> None:
    reply = await servicer_module.AuditServicer().AppendEvent(make_event(schema_version=0), context)
    assert reply.status == audit_pb2.APPEND_STATUS_ACCEPTED
    assert repository.calls[0]["schema_version"] == get_settings().schema_version


async def test_a_future_schema_version_is_refused(
    repository, allow_rate, caller_is_auth, context: FakeServicerContext
) -> None:
    reply = await servicer_module.AuditServicer().AppendEvent(make_event(schema_version=2), context)
    assert reply.status == audit_pb2.APPEND_STATUS_SCHEMA_UNSUPPORTED
    assert repository.calls == []


async def test_a_retired_schema_version_is_refused(
    repository,
    allow_rate,
    caller_is_auth,
    context: FakeServicerContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUDIT_MIN_ACCEPTED_SCHEMA_VERSION", "2")
    monkeypatch.setenv("AUDIT_SCHEMA_VERSION", "3")
    get_settings.cache_clear()
    reply = await servicer_module.AuditServicer().AppendEvent(make_event(schema_version=1), context)
    assert reply.status == audit_pb2.APPEND_STATUS_SCHEMA_UNSUPPORTED


async def test_an_unset_timestamp_is_rejected(
    repository, allow_rate, caller_is_auth, context: FakeServicerContext
) -> None:
    event = make_event()
    event.ClearField("occurred_at")
    reply = await servicer_module.AuditServicer().AppendEvent(event, context)
    assert reply.status == audit_pb2.APPEND_STATUS_REJECTED
    assert repository.calls == []


async def test_a_timestamp_beyond_the_skew_allowance_is_rejected(
    repository, allow_rate, caller_is_auth, context: FakeServicerContext
) -> None:
    ahead = datetime.now(UTC) + timedelta(seconds=get_settings().max_clock_skew_seconds + 60)
    reply = await servicer_module.AuditServicer().AppendEvent(
        make_event(occurred_at=ahead), context
    )
    assert reply.status == audit_pb2.APPEND_STATUS_REJECTED


async def test_a_timestamp_inside_the_skew_allowance_is_accepted(
    repository, allow_rate, caller_is_auth, context: FakeServicerContext
) -> None:
    ahead = datetime.now(UTC) + timedelta(seconds=get_settings().max_clock_skew_seconds - 60)
    reply = await servicer_module.AuditServicer().AppendEvent(
        make_event(occurred_at=ahead), context
    )
    assert reply.status == audit_pb2.APPEND_STATUS_ACCEPTED


async def test_a_timestamp_older_than_the_backdate_allowance_is_rejected(
    repository, allow_rate, caller_is_auth, context: FakeServicerContext
) -> None:
    behind = datetime.now(UTC) - timedelta(seconds=get_settings().max_backdate_seconds + 60)
    reply = await servicer_module.AuditServicer().AppendEvent(
        make_event(occurred_at=behind), context
    )
    assert reply.status == audit_pb2.APPEND_STATUS_REJECTED


async def test_a_timestamp_inside_the_backdate_allowance_is_accepted(
    repository, allow_rate, caller_is_auth, context: FakeServicerContext
) -> None:
    behind = datetime.now(UTC) - timedelta(seconds=get_settings().max_backdate_seconds - 60)
    reply = await servicer_module.AuditServicer().AppendEvent(
        make_event(occurred_at=behind), context
    )
    assert reply.status == audit_pb2.APPEND_STATUS_ACCEPTED


async def test_an_event_without_a_payload_is_rejected(
    repository, allow_rate, caller_is_auth, context: FakeServicerContext
) -> None:
    reply = await servicer_module.AuditServicer().AppendEvent(
        make_event(with_payload=False), context
    )
    assert reply.status == audit_pb2.APPEND_STATUS_REJECTED
    assert repository.calls == []


async def test_a_refused_rate_limit_stops_the_append(
    repository, caller_is_auth, context: FakeServicerContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def refuse(source_service: int) -> bool:
        return False

    monkeypatch.setattr(servicer_module, "check_append_rate", refuse)
    reply = await servicer_module.AuditServicer().AppendEvent(make_event(), context)
    assert reply.status == audit_pb2.APPEND_STATUS_RATE_LIMITED
    assert repository.calls == []


async def test_the_rate_limit_is_scoped_to_the_calling_service(
    repository, allow_rate, caller_is_auth, context: FakeServicerContext
) -> None:
    await servicer_module.AuditServicer().AppendEvent(make_event(), context)
    assert allow_rate == [common_pb2.SOURCE_SERVICE_AUTH]


async def test_the_rate_limit_is_checked_after_validation(
    repository, allow_rate, caller_is_auth, context: FakeServicerContext
) -> None:
    await servicer_module.AuditServicer().AppendEvent(make_event(event_id="bad"), context)
    assert allow_rate == []


async def test_a_constraint_violation_is_reported_as_rejected(
    repository, allow_rate, caller_is_auth, context: FakeServicerContext
) -> None:
    repository.error = IntegrityError("insert", {}, Exception("duplicate"))
    reply = await servicer_module.AuditServicer().AppendEvent(make_event(), context)
    assert reply.status == audit_pb2.APPEND_STATUS_REJECTED


async def test_a_store_failure_aborts_as_unavailable(
    repository, allow_rate, caller_is_auth, context: FakeServicerContext
) -> None:
    repository.error = OperationalError("select", {}, Exception("connection lost"))
    with pytest.raises(AbortError) as excinfo:
        await servicer_module.AuditServicer().AppendEvent(make_event(), context)
    assert excinfo.value.code == grpc.StatusCode.UNAVAILABLE


async def test_a_store_failure_does_not_leak_the_database_error(
    repository, allow_rate, caller_is_auth, context: FakeServicerContext
) -> None:
    repository.error = OperationalError("select", {}, Exception("password authentication failed"))
    with pytest.raises(AbortError) as excinfo:
        await servicer_module.AuditServicer().AppendEvent(make_event(), context)
    assert "password" not in excinfo.value.details


async def test_every_payload_kind_is_accepted(
    repository, allow_rate, caller_is_auth, context: FakeServicerContext
) -> None:
    for field in audit_pb2.AuditEvent.DESCRIPTOR.oneofs_by_name["payload"].fields:
        event = make_event(with_payload=False)
        getattr(event, field.name).SetInParent()
        reply = await servicer_module.AuditServicer().AppendEvent(event, context)
        assert reply.status == audit_pb2.APPEND_STATUS_ACCEPTED, field.name
