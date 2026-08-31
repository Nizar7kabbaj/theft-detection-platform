from __future__ import annotations

import pytest
from sqlalchemy import text

from app.core.chain import (
    GENESIS_CHECKPOINT_HASH,
    compute_chain_hash,
    compute_leaf_hash,
)
from app.core.signing import build_checkpoint_payload, get_signer
from app.repositories.audit_repository import (
    VERIFY_FAILURE_CHAIN_MISMATCH,
    VERIFY_FAILURE_CHECKPOINT_DIVERGENCE,
    VERIFY_FAILURE_CHECKPOINT_SIGNATURE_INVALID,
    VERIFY_FAILURE_LEAF_MISMATCH,
    VERIFY_FAILURE_LINKAGE_MISMATCH,
    VERIFY_FAILURE_MISSING_PAYLOAD,
    VERIFY_FAILURE_NONE,
    AuditRepository,
)
from app.services.checkpoint_service import verify_checkpoints
from tests.integration.test_append_chain import append_one

pytestmark = pytest.mark.integration


async def seed(session, count: int = 8) -> list:
    return [await append_one(session, actor=f"actor-{index % 4}") for index in range(count)]


async def write_checkpoint(session) -> None:
    events = AuditRepository(session)
    signer = get_signer()
    tail = await events.tail_state()
    payload = build_checkpoint_payload(
        key_id=signer.key_id,
        tree_size=tail.tree_size,
        tail_sequence_number=tail.tail_sequence_number,
        tail_chain_hash=tail.prev_hash,
        prev_checkpoint_hash=GENESIS_CHECKPOINT_HASH,
        signature_algorithm=signer.signature_algorithm,
    )
    await events.append_checkpoint(
        tail_sequence_number=tail.tail_sequence_number,
        tail_chain_hash=tail.prev_hash,
        tree_size=tail.tree_size,
        signature=signer.sign(payload),
        key_id=signer.key_id,
        prev_checkpoint_hash=GENESIS_CHECKPOINT_HASH,
        payload=payload,
        signature_algorithm=signer.signature_algorithm,
    )
    await session.commit()


async def test_an_untouched_chain_verifies(app_session) -> None:
    await seed(app_session)
    result = await AuditRepository(app_session).verify(None, None)
    assert result.chain_intact is True
    assert result.failure_kind == VERIFY_FAILURE_NONE
    assert result.events_verified == 8


async def test_a_tampered_payload_is_caught(app_session, owner_session) -> None:
    await seed(app_session)
    original = (
        await owner_session.execute(
            text("SELECT event_bytes FROM audit_events WHERE sequence_number = 3")
        )
    ).scalar_one()
    await owner_session.execute(text("SET LOCAL audit.maintenance = 'on'"))
    await owner_session.execute(
        text("UPDATE audit_events SET event_bytes = :b WHERE sequence_number = 3"),
        {"b": bytes(original) + b"\x00tampered"},
    )
    result = await AuditRepository(owner_session).verify(None, None)
    await owner_session.rollback()
    assert result.chain_intact is False
    assert result.break_at_sequence_number == 3
    assert result.failure_kind == VERIFY_FAILURE_LEAF_MISMATCH


async def test_a_tampered_payload_is_caught_at_the_right_row(app_session, owner_session) -> None:
    await seed(app_session)
    original = (
        await owner_session.execute(
            text("SELECT event_bytes FROM audit_events WHERE sequence_number = 6")
        )
    ).scalar_one()
    await owner_session.execute(text("SET LOCAL audit.maintenance = 'on'"))
    await owner_session.execute(
        text("UPDATE audit_events SET event_bytes = :b WHERE sequence_number = 6"),
        {"b": bytes(original) + b"\x00tampered"},
    )
    result = await AuditRepository(owner_session).verify(None, None)
    await owner_session.rollback()
    assert result.break_at_sequence_number == 6
    assert result.events_verified == 5


async def test_a_tombstoned_row_still_verifies(app_session, owner_session) -> None:
    await seed(app_session)
    await owner_session.execute(text("SET LOCAL audit.maintenance = 'on'"))
    await owner_session.execute(
        text(
            "UPDATE audit_events SET event_bytes = NULL, erased_at = now(), "
            "erasure_reason = 1 WHERE sequence_number = 5"
        )
    )
    result = await AuditRepository(owner_session).verify(None, None)
    await owner_session.rollback()
    assert result.chain_intact is True
    assert result.erased_rows_verified == 1
    assert result.events_verified == 7


async def test_several_tombstones_still_verify(app_session, owner_session) -> None:
    await seed(app_session)
    await owner_session.execute(text("SET LOCAL audit.maintenance = 'on'"))
    await owner_session.execute(
        text(
            "UPDATE audit_events SET event_bytes = NULL, erased_at = now(), "
            "erasure_reason = 1 WHERE sequence_number IN (2, 4, 7)"
        )
    )
    result = await AuditRepository(owner_session).verify(None, None)
    await owner_session.rollback()
    assert result.chain_intact is True
    assert result.erased_rows_verified == 3


async def test_a_missing_payload_without_a_tombstone_is_caught(app_session, owner_session) -> None:
    await seed(app_session)
    await owner_session.execute(text("SET LOCAL audit.maintenance = 'on'"))
    await owner_session.execute(
        text("ALTER TABLE audit_events DROP CONSTRAINT ck_audit_events_erasure_consistent")
    )
    await owner_session.execute(
        text("UPDATE audit_events SET event_bytes = NULL WHERE sequence_number = 4")
    )
    result = await AuditRepository(owner_session).verify(None, None)
    await owner_session.rollback()
    assert result.chain_intact is False
    assert result.break_at_sequence_number == 4
    assert result.failure_kind == VERIFY_FAILURE_MISSING_PAYLOAD


async def test_a_broken_link_is_caught(app_session, owner_session) -> None:
    await seed(app_session)
    await owner_session.execute(text("SET LOCAL audit.maintenance = 'on'"))
    await owner_session.execute(text("DROP TRIGGER trg_audit_events_no_update ON audit_events"))
    await owner_session.execute(
        text("UPDATE audit_events SET prev_hash = :h WHERE sequence_number = 5"),
        {"h": bytes(range(32))},
    )
    result = await AuditRepository(owner_session).verify(None, None)
    await owner_session.rollback()
    assert result.chain_intact is False
    assert result.break_at_sequence_number == 5
    assert result.failure_kind == VERIFY_FAILURE_LINKAGE_MISMATCH


async def test_a_recomputed_chain_hash_is_caught(app_session, owner_session) -> None:
    await seed(app_session)
    await owner_session.execute(text("SET LOCAL audit.maintenance = 'on'"))
    await owner_session.execute(text("DROP TRIGGER trg_audit_events_no_update ON audit_events"))
    await owner_session.execute(
        text("UPDATE audit_events SET chain_hash = :h WHERE sequence_number = 8"),
        {"h": bytes(range(32))},
    )
    result = await AuditRepository(owner_session).verify(None, None)
    await owner_session.rollback()
    assert result.chain_intact is False
    assert result.failure_kind == VERIFY_FAILURE_CHAIN_MISMATCH


async def test_a_deleted_row_breaks_the_linkage(app_session, owner_session) -> None:
    await seed(app_session)
    await owner_session.execute(text("SET LOCAL audit.maintenance = 'on'"))
    await owner_session.execute(text("DELETE FROM audit_events WHERE sequence_number = 4"))
    result = await AuditRepository(owner_session).verify(None, None)
    await owner_session.rollback()
    assert result.chain_intact is False
    assert result.break_at_sequence_number == 5
    assert result.failure_kind == VERIFY_FAILURE_LINKAGE_MISMATCH


async def test_a_signed_checkpoint_verifies(app_session) -> None:
    await seed(app_session)
    await write_checkpoint(app_session)
    result = await verify_checkpoints(AuditRepository(app_session))
    assert result.failure_kind == VERIFY_FAILURE_NONE
    assert result.checkpoints_verified == 1


async def test_a_fully_rewritten_history_passes_chain_verification(
    app_session, owner_session
) -> None:
    await seed(app_session)
    await write_checkpoint(app_session)
    await owner_session.execute(text("SET LOCAL audit.maintenance = 'on'"))
    await owner_session.execute(text("DROP TRIGGER trg_audit_events_no_update ON audit_events"))
    rows = (
        await owner_session.execute(
            text(
                "SELECT sequence_number, event_bytes FROM audit_events ORDER BY sequence_number ASC"
            )
        )
    ).all()
    prev = bytes(32)
    for sequence_number, event_bytes in rows:
        payload = bytes(event_bytes)
        if sequence_number == 4:
            payload = payload + b"\x00forged"
        leaf = compute_leaf_hash(payload)
        chain = compute_chain_hash(prev, leaf)
        await owner_session.execute(
            text(
                "UPDATE audit_events SET event_bytes = :b, leaf_hash = :l, "
                "prev_hash = :p, chain_hash = :c WHERE sequence_number = :s"
            ),
            {"b": payload, "l": leaf, "p": prev, "c": chain, "s": sequence_number},
        )
        prev = chain
    chain_result = await AuditRepository(owner_session).verify(None, None)
    await owner_session.rollback()
    assert chain_result.chain_intact is True


async def test_a_fully_rewritten_history_is_caught_by_the_checkpoint(
    app_session, owner_session
) -> None:
    await seed(app_session)
    await write_checkpoint(app_session)
    await owner_session.execute(text("SET LOCAL audit.maintenance = 'on'"))
    await owner_session.execute(text("DROP TRIGGER trg_audit_events_no_update ON audit_events"))
    rows = (
        await owner_session.execute(
            text(
                "SELECT sequence_number, event_bytes FROM audit_events ORDER BY sequence_number ASC"
            )
        )
    ).all()
    prev = bytes(32)
    for sequence_number, event_bytes in rows:
        payload = bytes(event_bytes)
        if sequence_number == 4:
            payload = payload + b"\x00forged"
        leaf = compute_leaf_hash(payload)
        chain = compute_chain_hash(prev, leaf)
        await owner_session.execute(
            text(
                "UPDATE audit_events SET event_bytes = :b, leaf_hash = :l, "
                "prev_hash = :p, chain_hash = :c WHERE sequence_number = :s"
            ),
            {"b": payload, "l": leaf, "p": prev, "c": chain, "s": sequence_number},
        )
        prev = chain
    checkpoint_result = await verify_checkpoints(AuditRepository(owner_session))
    await owner_session.rollback()
    assert checkpoint_result.failure_kind == VERIFY_FAILURE_CHECKPOINT_DIVERGENCE


async def test_a_forged_checkpoint_signature_is_caught(app_session, owner_session) -> None:
    await seed(app_session)
    await write_checkpoint(app_session)
    await owner_session.execute(
        text("ALTER TABLE audit_checkpoints DISABLE TRIGGER trg_audit_checkpoints_immutable")
    )
    await owner_session.execute(
        text("UPDATE audit_checkpoints SET signature = :s WHERE checkpoint_id = 1"),
        {"s": bytes(64)},
    )
    result = await verify_checkpoints(AuditRepository(owner_session))
    await owner_session.rollback()
    assert result.failure_kind == VERIFY_FAILURE_CHECKPOINT_SIGNATURE_INVALID


async def test_an_altered_checkpoint_tree_size_is_caught(app_session, owner_session) -> None:
    await seed(app_session)
    await write_checkpoint(app_session)
    await owner_session.execute(
        text("ALTER TABLE audit_checkpoints DISABLE TRIGGER trg_audit_checkpoints_immutable")
    )
    await owner_session.execute(
        text("UPDATE audit_checkpoints SET tree_size = 99 WHERE checkpoint_id = 1")
    )
    result = await verify_checkpoints(AuditRepository(owner_session))
    await owner_session.rollback()
    assert result.failure_kind == VERIFY_FAILURE_CHECKPOINT_DIVERGENCE


async def test_a_checkpoint_not_linked_to_genesis_is_caught(app_session, owner_session) -> None:
    await seed(app_session)
    await write_checkpoint(app_session)
    await owner_session.execute(
        text("ALTER TABLE audit_checkpoints DISABLE TRIGGER trg_audit_checkpoints_immutable")
    )
    await owner_session.execute(
        text("UPDATE audit_checkpoints SET prev_checkpoint_hash = :h WHERE checkpoint_id = 1"),
        {"h": bytes(range(32))},
    )
    result = await verify_checkpoints(AuditRepository(owner_session))
    await owner_session.rollback()
    assert result.failure_kind == VERIFY_FAILURE_CHECKPOINT_DIVERGENCE


async def test_an_empty_log_verifies(app_session) -> None:
    result = await AuditRepository(app_session).verify(None, None)
    assert result.chain_intact is True
    assert result.events_verified == 0


async def test_an_empty_checkpoint_table_verifies(app_session) -> None:
    result = await verify_checkpoints(AuditRepository(app_session))
    assert result.failure_kind == VERIFY_FAILURE_NONE
    assert result.checkpoints_verified == 0
