from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.chain import genesis_prev_hash
from app.server.grpc_gen import audit_pb2
from tests.integration.test_append_chain import append_one

pytestmark = pytest.mark.integration


LIFECYCLE_KIND = audit_pb2.AuditEvent.DESCRIPTOR.fields_by_name["service_lifecycle"].number


async def test_an_update_outside_maintenance_is_refused(owner_session, app_session) -> None:
    result = await append_one(app_session)
    with pytest.raises(DBAPIError, match="append-only"):
        await owner_session.execute(
            text("UPDATE audit_events SET actor = 'changed' WHERE sequence_number = :s"),
            {"s": result.sequence_number},
        )
    await owner_session.rollback()


async def test_a_delete_outside_maintenance_is_refused(owner_session, app_session) -> None:
    result = await append_one(app_session)
    with pytest.raises(DBAPIError, match="append-only"):
        await owner_session.execute(
            text("DELETE FROM audit_events WHERE sequence_number = :s"),
            {"s": result.sequence_number},
        )
    await owner_session.rollback()


async def test_the_refused_update_leaves_the_row_untouched(owner_session, app_session) -> None:
    result = await append_one(app_session, actor="original")
    with pytest.raises(DBAPIError):
        await owner_session.execute(
            text("UPDATE audit_events SET actor = 'changed' WHERE sequence_number = :s"),
            {"s": result.sequence_number},
        )
    await owner_session.rollback()
    actor = (
        await app_session.execute(
            text("SELECT actor FROM audit_events WHERE sequence_number = :s"),
            {"s": result.sequence_number},
        )
    ).scalar_one()
    assert actor == "original"


async def test_maintenance_permits_a_tombstone_update(owner_session, app_session) -> None:
    result = await append_one(app_session)
    await owner_session.execute(text("SET LOCAL audit.maintenance = 'on'"))
    await owner_session.execute(
        text(
            "UPDATE audit_events SET event_bytes = NULL, erased_at = now(), "
            "erasure_reason = 1 WHERE sequence_number = :s"
        ),
        {"s": result.sequence_number},
    )
    await owner_session.commit()
    erased = (
        await app_session.execute(
            text("SELECT erased_at FROM audit_events WHERE sequence_number = :s"),
            {"s": result.sequence_number},
        )
    ).scalar_one()
    assert erased is not None


async def test_maintenance_permits_a_delete(owner_session, app_session) -> None:
    result = await append_one(app_session)
    await owner_session.execute(text("SET LOCAL audit.maintenance = 'on'"))
    await owner_session.execute(
        text("DELETE FROM audit_events WHERE sequence_number = :s"),
        {"s": result.sequence_number},
    )
    await owner_session.commit()
    count = (await app_session.execute(text("SELECT count(*) FROM audit_events"))).scalar_one()
    assert count == 0


async def test_maintenance_still_refuses_to_change_the_leaf_hash(
    owner_session, app_session
) -> None:
    result = await append_one(app_session)
    await owner_session.execute(text("SET LOCAL audit.maintenance = 'on'"))
    with pytest.raises(DBAPIError, match="chain columns are immutable"):
        await owner_session.execute(
            text("UPDATE audit_events SET leaf_hash = :h WHERE sequence_number = :s"),
            {"h": bytes(range(32)), "s": result.sequence_number},
        )
    await owner_session.rollback()


async def test_maintenance_still_refuses_to_change_the_chain_hash(
    owner_session, app_session
) -> None:
    result = await append_one(app_session)
    await owner_session.execute(text("SET LOCAL audit.maintenance = 'on'"))
    with pytest.raises(DBAPIError, match="chain columns are immutable"):
        await owner_session.execute(
            text("UPDATE audit_events SET chain_hash = :h WHERE sequence_number = :s"),
            {"h": bytes(range(32)), "s": result.sequence_number},
        )
    await owner_session.rollback()


async def test_maintenance_still_refuses_to_change_the_prev_hash(
    owner_session, app_session
) -> None:
    result = await append_one(app_session)
    await owner_session.execute(text("SET LOCAL audit.maintenance = 'on'"))
    with pytest.raises(DBAPIError, match="chain columns are immutable"):
        await owner_session.execute(
            text("UPDATE audit_events SET prev_hash = :h WHERE sequence_number = :s"),
            {"h": bytes(range(32)), "s": result.sequence_number},
        )
    await owner_session.rollback()


async def test_maintenance_still_refuses_to_change_the_event_id(owner_session, app_session) -> None:
    result = await append_one(app_session)
    await owner_session.execute(text("SET LOCAL audit.maintenance = 'on'"))
    with pytest.raises(DBAPIError, match="chain columns are immutable"):
        await owner_session.execute(
            text("UPDATE audit_events SET event_id = :e WHERE sequence_number = :s"),
            {"e": str(uuid.uuid4()), "s": result.sequence_number},
        )
    await owner_session.rollback()


async def test_maintenance_still_refuses_to_change_the_timestamps(
    owner_session, app_session
) -> None:
    result = await append_one(app_session)
    await owner_session.execute(text("SET LOCAL audit.maintenance = 'on'"))
    with pytest.raises(DBAPIError, match="chain columns are immutable"):
        await owner_session.execute(
            text("UPDATE audit_events SET occurred_at = now() WHERE sequence_number = :s"),
            {"s": result.sequence_number},
        )
    await owner_session.rollback()


async def test_the_maintenance_flag_does_not_survive_the_transaction(
    owner_session, app_session
) -> None:
    result = await append_one(app_session)
    await owner_session.execute(text("SET LOCAL audit.maintenance = 'on'"))
    await owner_session.commit()
    with pytest.raises(DBAPIError, match="append-only"):
        await owner_session.execute(
            text("DELETE FROM audit_events WHERE sequence_number = :s"),
            {"s": result.sequence_number},
        )
    await owner_session.rollback()


async def test_a_checkpoint_cannot_be_updated_even_under_maintenance(owner_session) -> None:
    await owner_session.execute(
        text(
            """
            INSERT INTO audit_checkpoints (
                tail_sequence_number, tail_chain_hash, tree_size, hash_algorithm,
                signature_algorithm, signature, key_id,
                prev_checkpoint_hash, checkpoint_hash
            ) VALUES (1, :tail, 1, 1, 1, :signature, 'c1', :prev, :hash)
            """
        ),
        {
            "tail": bytes(range(32)),
            "signature": bytes(64),
            "prev": bytes(32),
            "hash": bytes(range(32, 64)),
        },
    )
    await owner_session.commit()
    await owner_session.execute(text("SET LOCAL audit.maintenance = 'on'"))
    with pytest.raises(DBAPIError, match="append-only"):
        await owner_session.execute(text("UPDATE audit_checkpoints SET key_id = 'c2'"))
    await owner_session.rollback()


async def test_a_checkpoint_cannot_be_deleted_even_under_maintenance(owner_session) -> None:
    await owner_session.execute(
        text(
            """
            INSERT INTO audit_checkpoints (
                tail_sequence_number, tail_chain_hash, tree_size, hash_algorithm,
                signature_algorithm, signature, key_id,
                prev_checkpoint_hash, checkpoint_hash
            ) VALUES (1, :tail, 1, 1, 1, :signature, 'c1', :prev, :hash)
            """
        ),
        {
            "tail": bytes(range(32)),
            "signature": bytes(64),
            "prev": bytes(32),
            "hash": bytes(range(32, 64)),
        },
    )
    await owner_session.commit()
    await owner_session.execute(text("SET LOCAL audit.maintenance = 'on'"))
    with pytest.raises(DBAPIError, match="append-only"):
        await owner_session.execute(text("DELETE FROM audit_checkpoints"))
    await owner_session.rollback()


async def test_a_sealed_segment_cannot_be_updated(owner_session) -> None:
    await owner_session.execute(
        text(
            """
            INSERT INTO audit_chain_segments (
                first_sequence_number, last_sequence_number, first_prev_hash,
                terminal_chain_hash, row_count, hash_algorithm, covers_from, covers_to
            ) VALUES (1, 5, :first, :terminal, 5, 1, now(), now())
            """
        ),
        {"first": genesis_prev_hash(), "terminal": bytes(range(32))},
    )
    await owner_session.commit()
    await owner_session.execute(text("SET LOCAL audit.maintenance = 'on'"))
    with pytest.raises(DBAPIError, match="immutable once sealed"):
        await owner_session.execute(text("UPDATE audit_chain_segments SET row_count = 9"))
    await owner_session.rollback()


async def test_a_segment_delete_outside_maintenance_is_refused(owner_session) -> None:
    await owner_session.execute(
        text(
            """
            INSERT INTO audit_chain_segments (
                first_sequence_number, last_sequence_number, first_prev_hash,
                terminal_chain_hash, row_count, hash_algorithm, covers_from, covers_to
            ) VALUES (1, 5, :first, :terminal, 5, 1, now(), now())
            """
        ),
        {"first": genesis_prev_hash(), "terminal": bytes(range(32))},
    )
    await owner_session.commit()
    with pytest.raises(DBAPIError, match="denied outside maintenance"):
        await owner_session.execute(text("DELETE FROM audit_chain_segments"))
    await owner_session.rollback()


async def test_an_insert_is_never_blocked_by_the_trigger(app_session) -> None:
    for _ in range(3):
        await append_one(app_session)
    count = (await app_session.execute(text("SELECT count(*) FROM audit_events"))).scalar_one()
    assert count == 3
