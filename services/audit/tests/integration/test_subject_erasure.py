from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from app.repositories.audit_repository import (
    VERIFY_FAILURE_NONE,
    AuditRepository,
    extract_subjects,
)
from app.server.grpc_gen import audit_pb2 as pb
from app.server.grpc_gen import common_pb2
from tests.integration.test_append_chain import append_one

pytestmark = pytest.mark.integration

ADMIN_ACTION_KIND = 27
ERASURE_REASON_ACCOUNT_DELETED = 2


def admin_action_payload(actor_id: str, target_id: str) -> bytes:
    event = pb.AuditEvent(
        schema_version=1,
        event_id=str(uuid.uuid4()),
        source_service=common_pb2.SOURCE_SERVICE_AUTH,
        actor=actor_id,
        severity=common_pb2.SEVERITY_NOTICE,
    )
    event.occurred_at.FromDatetime(datetime.now(UTC))
    payload = event.admin_action
    payload.actor_user_id = actor_id
    payload.action = pb.ADMIN_ACTION_KIND_DISABLE
    payload.target_kind = pb.ADMIN_TARGET_KIND_USER
    payload.target_id = target_id
    payload.reason_code = pb.ADMIN_REASON_CODE_OFFBOARDING
    return event.SerializeToString(deterministic=True)


async def append_admin_action(session, actor_id: str, target_id: str):
    return await append_one(
        session,
        actor=actor_id,
        event_bytes=admin_action_payload(actor_id, target_id),
        payload_kind=ADMIN_ACTION_KIND,
        severity=common_pb2.SEVERITY_NOTICE,
    )


def test_subjects_carry_actor_and_target() -> None:
    payload = admin_action_payload("actor-uuid", "target-uuid")
    assert extract_subjects(payload) == ["actor-uuid", "target-uuid"]


def test_subjects_survive_a_corrupt_payload() -> None:
    assert extract_subjects(b"not a protobuf message at all") == []


async def test_an_appended_event_records_both_subjects(app_session) -> None:
    result = await append_admin_action(app_session, "actor-uuid", "target-uuid")
    stored = (
        await app_session.execute(
            text("SELECT subjects FROM audit_events WHERE sequence_number = :s"),
            {"s": result.sequence_number},
        )
    ).scalar_one()
    assert sorted(stored) == ["actor-uuid", "target-uuid"]


async def test_erasure_destroys_the_payload_and_marks_the_row(owner_session) -> None:
    await append_admin_action(owner_session, "erase-actor", "erase-target")
    erased = await AuditRepository(owner_session).erase_subject_payloads(
        "erase-target",
        ERASURE_REASON_ACCOUNT_DELETED,
    )
    await owner_session.commit()
    assert erased == 1
    row = (
        await owner_session.execute(
            text(
                "SELECT event_bytes, erased_at, erasure_reason FROM audit_events "
                "WHERE subjects @> ARRAY['erase-target']::varchar[]"
            )
        )
    ).one()
    assert row[0] is None
    assert row[1] is not None
    assert row[2] == ERASURE_REASON_ACCOUNT_DELETED


async def test_erasure_reaches_a_person_named_only_as_the_target(owner_session) -> None:
    await append_admin_action(owner_session, "keeper-actor", "victim-target")
    erased = await AuditRepository(owner_session).erase_subject_payloads(
        "victim-target",
        ERASURE_REASON_ACCOUNT_DELETED,
    )
    await owner_session.commit()
    assert erased == 1


async def test_erasure_leaves_other_people_untouched(owner_session) -> None:
    kept = await append_one(owner_session, actor="bystander")
    await append_admin_action(owner_session, "gone-actor", "gone-target")
    await AuditRepository(owner_session).erase_subject_payloads(
        "gone-target",
        ERASURE_REASON_ACCOUNT_DELETED,
    )
    await owner_session.commit()
    payload = (
        await owner_session.execute(
            text("SELECT event_bytes FROM audit_events WHERE sequence_number = :s"),
            {"s": kept.sequence_number},
        )
    ).scalar_one()
    assert payload is not None


async def test_erasure_is_idempotent(owner_session) -> None:
    await append_admin_action(owner_session, "twice-actor", "twice-target")
    events = AuditRepository(owner_session)
    first = await events.erase_subject_payloads("twice-target", ERASURE_REASON_ACCOUNT_DELETED)
    await owner_session.commit()
    second = await events.erase_subject_payloads("twice-target", ERASURE_REASON_ACCOUNT_DELETED)
    await owner_session.commit()
    assert first == 1
    assert second == 0


async def test_the_chain_still_verifies_after_an_erasure(owner_session) -> None:
    for index in range(4):
        await append_one(owner_session, actor=f"chain-actor-{index}")
    await append_admin_action(owner_session, "chain-admin", "chain-subject")
    for index in range(4):
        await append_one(owner_session, actor=f"chain-tail-{index}")
    events = AuditRepository(owner_session)
    await events.erase_subject_payloads("chain-subject", ERASURE_REASON_ACCOUNT_DELETED)
    await owner_session.commit()
    result = await events.verify(None, None)
    assert result.chain_intact is True
    assert result.failure_kind == VERIFY_FAILURE_NONE
    assert result.erased_rows_verified >= 1
