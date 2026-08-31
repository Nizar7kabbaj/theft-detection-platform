from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import ClassVar

import grpc
import pytest
from sqlalchemy.exc import OperationalError

from app.repositories.audit_repository import (
    VERIFY_FAILURE_CHAIN_MISMATCH,
    VERIFY_FAILURE_CHECKPOINT_DIVERGENCE,
    VERIFY_FAILURE_CHECKPOINT_SIGNATURE_INVALID,
    VERIFY_FAILURE_LEAF_MISMATCH,
    VERIFY_FAILURE_NONE,
    VerifyResult,
)
from app.server import servicer as servicer_module
from app.server.grpc_gen import audit_pb2, common_pb2
from tests.conftest import AbortError, FakeServicerContext

pytestmark = pytest.mark.unit


VERIFY_KIND = audit_pb2.AuditEvent.DESCRIPTOR.fields_by_name["audit_log_accessed"].number


@dataclass
class CheckpointOutcome:
    failure_kind: int
    checkpoints_verified: int


@dataclass
class StoredCheckpoint:
    checkpoint_id: int = 3
    tail_sequence_number: int = 42
    tail_chain_hash: bytes = bytes(range(32))
    tree_size: int = 42
    hash_algorithm: int = 1
    signature_algorithm: int = 1
    signature: bytes = bytes(64)
    key_id: str = "c1"
    signed_at: datetime = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)
    prev_checkpoint_hash: bytes = bytes(32)
    checkpoint_hash: bytes = bytes(range(32, 64))


class FakeSession:
    def __init__(self) -> None:
        self.committed = False

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, *exc_info) -> bool:
        return False

    async def commit(self) -> None:
        self.committed = True


class VerifyRepository:
    verify_result = VerifyResult(True, None, VERIFY_FAILURE_NONE, 10, 0, 0)
    verify_calls: ClassVar[list[dict]] = []
    append_calls: ClassVar[list[dict]] = []
    verify_error: Exception | None = None
    checkpoint: StoredCheckpoint | None = None
    checkpoint_by_id_calls: ClassVar[list[int]] = []
    latest_checkpoint_calls = 0

    def __init__(self, session) -> None:
        self.session = session

    async def verify(self, **kwargs) -> VerifyResult:
        VerifyRepository.verify_calls.append(kwargs)
        if VerifyRepository.verify_error is not None:
            raise VerifyRepository.verify_error
        return VerifyRepository.verify_result

    async def append(self, **kwargs):
        VerifyRepository.append_calls.append(kwargs)

    async def checkpoint_by_id(self, checkpoint_id: int):
        VerifyRepository.checkpoint_by_id_calls.append(checkpoint_id)
        if VerifyRepository.verify_error is not None:
            raise VerifyRepository.verify_error
        return VerifyRepository.checkpoint

    async def latest_checkpoint(self):
        VerifyRepository.latest_checkpoint_calls += 1
        if VerifyRepository.verify_error is not None:
            raise VerifyRepository.verify_error
        return VerifyRepository.checkpoint


@pytest.fixture
def repository(monkeypatch: pytest.MonkeyPatch):
    VerifyRepository.verify_result = VerifyResult(True, None, VERIFY_FAILURE_NONE, 10, 0, 0)
    VerifyRepository.verify_calls = []
    VerifyRepository.append_calls = []
    VerifyRepository.verify_error = None
    VerifyRepository.checkpoint = None
    VerifyRepository.checkpoint_by_id_calls = []
    VerifyRepository.latest_checkpoint_calls = 0
    session = FakeSession()
    monkeypatch.setattr(servicer_module, "get_sessionmaker", lambda: lambda: session)
    monkeypatch.setattr(servicer_module, "AuditRepository", VerifyRepository)
    VerifyRepository.session = session
    return VerifyRepository


@pytest.fixture
def checkpoints_intact(monkeypatch: pytest.MonkeyPatch):
    async def verify_checkpoints(events):
        return CheckpointOutcome(VERIFY_FAILURE_NONE, 2)

    monkeypatch.setattr(servicer_module, "verify_checkpoints", verify_checkpoints)


def _checkpoints_failing(monkeypatch: pytest.MonkeyPatch, kind: int, verified: int = 2) -> None:
    async def verify_checkpoints(events):
        return CheckpointOutcome(kind, verified)

    monkeypatch.setattr(servicer_module, "verify_checkpoints", verify_checkpoints)


async def test_an_intact_chain_is_reported_intact(
    repository, checkpoints_intact, context: FakeServicerContext
) -> None:
    reply = await servicer_module.AuditServicer().VerifyChain(
        audit_pb2.VerifyChainRequest(), context
    )
    assert reply.chain_intact is True
    assert reply.failure_kind == VERIFY_FAILURE_NONE
    assert reply.break_at_sequence_number == ""


async def test_the_verified_counts_are_reported(
    repository, checkpoints_intact, context: FakeServicerContext
) -> None:
    repository.verify_result = VerifyResult(True, None, VERIFY_FAILURE_NONE, 38, 2, 0)
    reply = await servicer_module.AuditServicer().VerifyChain(
        audit_pb2.VerifyChainRequest(), context
    )
    assert reply.events_verified == 38
    assert reply.erased_rows_verified == 2
    assert reply.checkpoints_verified == 2


async def test_a_broken_chain_reports_the_break_position(
    repository, checkpoints_intact, context: FakeServicerContext
) -> None:
    repository.verify_result = VerifyResult(False, 17, VERIFY_FAILURE_LEAF_MISMATCH, 16, 0, 0)
    reply = await servicer_module.AuditServicer().VerifyChain(
        audit_pb2.VerifyChainRequest(), context
    )
    assert reply.chain_intact is False
    assert reply.break_at_sequence_number == "17"
    assert reply.failure_kind == VERIFY_FAILURE_LEAF_MISMATCH


async def test_a_chain_failure_keeps_its_own_failure_kind(
    repository, context: FakeServicerContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _checkpoints_failing(monkeypatch, VERIFY_FAILURE_CHECKPOINT_DIVERGENCE)
    repository.verify_result = VerifyResult(False, 9, VERIFY_FAILURE_CHAIN_MISMATCH, 8, 0, 0)
    reply = await servicer_module.AuditServicer().VerifyChain(
        audit_pb2.VerifyChainRequest(), context
    )
    assert reply.failure_kind == VERIFY_FAILURE_CHAIN_MISMATCH


async def test_a_rewritten_history_is_caught_by_the_checkpoints(
    repository, context: FakeServicerContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _checkpoints_failing(monkeypatch, VERIFY_FAILURE_CHECKPOINT_DIVERGENCE)
    reply = await servicer_module.AuditServicer().VerifyChain(
        audit_pb2.VerifyChainRequest(), context
    )
    assert reply.chain_intact is False
    assert reply.failure_kind == VERIFY_FAILURE_CHECKPOINT_DIVERGENCE


async def test_an_invalid_checkpoint_signature_breaks_verification(
    repository, context: FakeServicerContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _checkpoints_failing(monkeypatch, VERIFY_FAILURE_CHECKPOINT_SIGNATURE_INVALID)
    reply = await servicer_module.AuditServicer().VerifyChain(
        audit_pb2.VerifyChainRequest(), context
    )
    assert reply.chain_intact is False
    assert reply.failure_kind == VERIFY_FAILURE_CHECKPOINT_SIGNATURE_INVALID


async def test_an_empty_range_verifies_the_whole_chain(
    repository, checkpoints_intact, context: FakeServicerContext
) -> None:
    await servicer_module.AuditServicer().VerifyChain(audit_pb2.VerifyChainRequest(), context)
    call = repository.verify_calls[0]
    assert call["from_sequence_number"] is None
    assert call["to_sequence_number"] is None


async def test_a_bounded_range_is_passed_through(
    repository, checkpoints_intact, context: FakeServicerContext
) -> None:
    await servicer_module.AuditServicer().VerifyChain(
        audit_pb2.VerifyChainRequest(from_sequence_number="5", to_sequence_number="20"),
        context,
    )
    call = repository.verify_calls[0]
    assert call["from_sequence_number"] == 5
    assert call["to_sequence_number"] == 20


@pytest.mark.parametrize("start", ["abc", "-1", "1.5", "x9"])
async def test_a_malformed_start_is_refused(
    repository, checkpoints_intact, context: FakeServicerContext, start: str
) -> None:
    with pytest.raises(AbortError) as excinfo:
        await servicer_module.AuditServicer().VerifyChain(
            audit_pb2.VerifyChainRequest(from_sequence_number=start), context
        )
    assert excinfo.value.code == grpc.StatusCode.INVALID_ARGUMENT


async def test_a_malformed_end_is_refused(
    repository, checkpoints_intact, context: FakeServicerContext
) -> None:
    with pytest.raises(AbortError) as excinfo:
        await servicer_module.AuditServicer().VerifyChain(
            audit_pb2.VerifyChainRequest(to_sequence_number="later"), context
        )
    assert excinfo.value.code == grpc.StatusCode.INVALID_ARGUMENT


async def test_a_malformed_range_does_not_reach_the_store(
    repository, checkpoints_intact, context: FakeServicerContext
) -> None:
    with pytest.raises(AbortError):
        await servicer_module.AuditServicer().VerifyChain(
            audit_pb2.VerifyChainRequest(from_sequence_number="abc"), context
        )
    assert repository.verify_calls == []


async def test_the_verification_is_recorded_in_the_log(
    repository, checkpoints_intact, context: FakeServicerContext
) -> None:
    await servicer_module.AuditServicer().VerifyChain(audit_pb2.VerifyChainRequest(), context)
    assert len(repository.append_calls) == 1
    assert repository.append_calls[0]["payload_kind"] == VERIFY_KIND


async def test_the_verification_record_names_the_verify_scope(
    repository, checkpoints_intact, context: FakeServicerContext
) -> None:
    await servicer_module.AuditServicer().VerifyChain(audit_pb2.VerifyChainRequest(), context)
    recorded = audit_pb2.AuditEvent()
    recorded.ParseFromString(repository.append_calls[0]["event_bytes"])
    assert recorded.audit_log_accessed.scope == audit_pb2.AUDIT_QUERY_SCOPE_VERIFY


async def test_the_verification_record_counts_the_events_verified(
    repository, checkpoints_intact, context: FakeServicerContext
) -> None:
    repository.verify_result = VerifyResult(True, None, VERIFY_FAILURE_NONE, 38, 0, 0)
    await servicer_module.AuditServicer().VerifyChain(audit_pb2.VerifyChainRequest(), context)
    recorded = audit_pb2.AuditEvent()
    recorded.ParseFromString(repository.append_calls[0]["event_bytes"])
    assert recorded.audit_log_accessed.rows_returned == 38


async def test_a_store_failure_during_verification_aborts_as_unavailable(
    repository, checkpoints_intact, context: FakeServicerContext
) -> None:
    repository.verify_error = OperationalError("select", {}, Exception("connection lost"))
    with pytest.raises(AbortError) as excinfo:
        await servicer_module.AuditServicer().VerifyChain(audit_pb2.VerifyChainRequest(), context)
    assert excinfo.value.code == grpc.StatusCode.UNAVAILABLE


async def test_an_absent_checkpoint_is_reported_as_not_found(
    repository, context: FakeServicerContext
) -> None:
    reply = await servicer_module.AuditServicer().GetCheckpoint(
        audit_pb2.GetCheckpointRequest(), context
    )
    assert reply.found is False
    assert reply.HasField("checkpoint") is False


async def test_an_absent_checkpoint_id_reads_the_latest(
    repository, context: FakeServicerContext
) -> None:
    repository.checkpoint = StoredCheckpoint()
    await servicer_module.AuditServicer().GetCheckpoint(audit_pb2.GetCheckpointRequest(), context)
    assert repository.latest_checkpoint_calls == 1
    assert repository.checkpoint_by_id_calls == []


async def test_a_given_checkpoint_id_is_read_directly(
    repository, context: FakeServicerContext
) -> None:
    repository.checkpoint = StoredCheckpoint()
    await servicer_module.AuditServicer().GetCheckpoint(
        audit_pb2.GetCheckpointRequest(checkpoint_id=3), context
    )
    assert repository.checkpoint_by_id_calls == [3]
    assert repository.latest_checkpoint_calls == 0


async def test_a_found_checkpoint_is_returned_in_full(
    repository, context: FakeServicerContext
) -> None:
    repository.checkpoint = StoredCheckpoint()
    reply = await servicer_module.AuditServicer().GetCheckpoint(
        audit_pb2.GetCheckpointRequest(checkpoint_id=3), context
    )
    assert reply.found is True
    assert reply.checkpoint.checkpoint_id == 3
    assert reply.checkpoint.tail_sequence_number == "42"
    assert reply.checkpoint.tail_chain_hash == bytes(range(32))
    assert reply.checkpoint.key_id == "c1"


async def test_a_checkpoint_read_is_recorded_in_the_log(
    repository, context: FakeServicerContext
) -> None:
    repository.checkpoint = StoredCheckpoint()
    await servicer_module.AuditServicer().GetCheckpoint(
        audit_pb2.GetCheckpointRequest(checkpoint_id=3), context
    )
    recorded = audit_pb2.AuditEvent()
    recorded.ParseFromString(repository.append_calls[0]["event_bytes"])
    assert recorded.audit_log_accessed.scope == audit_pb2.AUDIT_QUERY_SCOPE_CHECKPOINT
    assert recorded.audit_log_accessed.rows_returned == 1


async def test_a_missing_checkpoint_read_records_zero_rows(
    repository, context: FakeServicerContext
) -> None:
    await servicer_module.AuditServicer().GetCheckpoint(
        audit_pb2.GetCheckpointRequest(checkpoint_id=99), context
    )
    recorded = audit_pb2.AuditEvent()
    recorded.ParseFromString(repository.append_calls[0]["event_bytes"])
    assert recorded.audit_log_accessed.rows_returned == 0


async def test_a_store_failure_during_a_checkpoint_read_aborts_as_unavailable(
    repository, context: FakeServicerContext
) -> None:
    repository.verify_error = OperationalError("select", {}, Exception("connection lost"))
    with pytest.raises(AbortError) as excinfo:
        await servicer_module.AuditServicer().GetCheckpoint(
            audit_pb2.GetCheckpointRequest(), context
        )
    assert excinfo.value.code == grpc.StatusCode.UNAVAILABLE


async def test_the_access_record_is_attributed_to_the_audit_service(
    repository, context: FakeServicerContext
) -> None:
    await servicer_module.AuditServicer().GetCheckpoint(audit_pb2.GetCheckpointRequest(), context)
    assert repository.append_calls[0]["source_service"] == common_pb2.SOURCE_SERVICE_AUDIT
