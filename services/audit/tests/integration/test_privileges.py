from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from app.core.chain import genesis_prev_hash
from app.server.grpc_gen import audit_pb2
from tests.integration.test_append_chain import append_one

pytestmark = pytest.mark.integration


LIFECYCLE_KIND = audit_pb2.AuditEvent.DESCRIPTOR.fields_by_name["service_lifecycle"].number


async def test_the_app_role_can_insert_events(app_session) -> None:
    result = await append_one(app_session)
    assert result.sequence_number == 1


async def test_the_app_role_can_read_events(app_session) -> None:
    await append_one(app_session)
    count = (await app_session.execute(text("SELECT count(*) FROM audit_events"))).scalar_one()
    assert count == 1


async def test_the_app_role_cannot_update_events(app_session) -> None:
    result = await append_one(app_session)
    with pytest.raises(ProgrammingError, match="permission denied"):
        await app_session.execute(
            text("UPDATE audit_events SET actor = 'changed' WHERE sequence_number = :s"),
            {"s": result.sequence_number},
        )
    await app_session.rollback()


async def test_the_app_role_cannot_delete_events(app_session) -> None:
    result = await append_one(app_session)
    with pytest.raises(ProgrammingError, match="permission denied"):
        await app_session.execute(
            text("DELETE FROM audit_events WHERE sequence_number = :s"),
            {"s": result.sequence_number},
        )
    await app_session.rollback()


async def test_maintenance_does_not_grant_the_app_role_a_delete(app_session) -> None:
    result = await append_one(app_session)
    await app_session.execute(text("SET LOCAL audit.maintenance = 'on'"))
    with pytest.raises(ProgrammingError, match="permission denied"):
        await app_session.execute(
            text("DELETE FROM audit_events WHERE sequence_number = :s"),
            {"s": result.sequence_number},
        )
    await app_session.rollback()


async def test_maintenance_does_not_grant_the_app_role_an_update(app_session) -> None:
    result = await append_one(app_session)
    await app_session.execute(text("SET LOCAL audit.maintenance = 'on'"))
    with pytest.raises(ProgrammingError, match="permission denied"):
        await app_session.execute(
            text("UPDATE audit_events SET actor = 'changed' WHERE sequence_number = :s"),
            {"s": result.sequence_number},
        )
    await app_session.rollback()


async def test_the_app_role_cannot_truncate_events(app_session) -> None:
    await append_one(app_session)
    with pytest.raises(ProgrammingError, match="permission denied"):
        await app_session.execute(text("TRUNCATE audit_events"))
    await app_session.rollback()


async def test_the_app_role_cannot_drop_the_table(app_session) -> None:
    with pytest.raises(ProgrammingError, match="must be owner"):
        await app_session.execute(text("DROP TABLE audit_events"))
    await app_session.rollback()


async def test_the_app_role_cannot_drop_the_guard_trigger(app_session) -> None:
    with pytest.raises(ProgrammingError, match="must be owner"):
        await app_session.execute(text("DROP TRIGGER trg_audit_events_no_update ON audit_events"))
    await app_session.rollback()


async def test_the_app_role_can_insert_a_checkpoint(app_session) -> None:
    await app_session.execute(
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
    await app_session.commit()
    count = (await app_session.execute(text("SELECT count(*) FROM audit_checkpoints"))).scalar_one()
    assert count == 1


async def test_the_app_role_cannot_delete_a_checkpoint(app_session) -> None:
    with pytest.raises(ProgrammingError, match="permission denied"):
        await app_session.execute(text("DELETE FROM audit_checkpoints"))
    await app_session.rollback()


async def test_the_app_role_can_read_segments(app_session) -> None:
    count = (
        await app_session.execute(text("SELECT count(*) FROM audit_chain_segments"))
    ).scalar_one()
    assert count == 0


async def test_the_app_role_cannot_insert_a_segment(app_session) -> None:
    with pytest.raises(ProgrammingError, match="permission denied"):
        await app_session.execute(
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
    await app_session.rollback()


async def test_the_app_role_cannot_read_the_migration_history(app_session) -> None:
    with pytest.raises(ProgrammingError, match="permission denied"):
        await app_session.execute(text("SELECT * FROM alembic_version"))
    await app_session.rollback()


async def test_the_owner_role_can_read_the_migration_history(owner_session) -> None:
    version = (
        await owner_session.execute(text("SELECT version_num FROM alembic_version"))
    ).scalar_one()
    assert version == "a1b2c3d4e5f6"


async def test_the_owner_role_can_delete_under_maintenance(owner_session, app_session) -> None:
    result = await append_one(app_session)
    await owner_session.execute(text("SET LOCAL audit.maintenance = 'on'"))
    await owner_session.execute(
        text("DELETE FROM audit_events WHERE sequence_number = :s"),
        {"s": result.sequence_number},
    )
    await owner_session.commit()
    count = (await app_session.execute(text("SELECT count(*) FROM audit_events"))).scalar_one()
    assert count == 0


async def test_the_two_roles_are_genuinely_different(app_session, owner_session) -> None:
    app_user = (await app_session.execute(text("SELECT current_user"))).scalar_one()
    owner_user = (await owner_session.execute(text("SELECT current_user"))).scalar_one()
    assert app_user == "audit_app"
    assert owner_user == "audit_owner"


async def test_the_app_role_is_not_a_superuser(app_session) -> None:
    is_super = (
        await app_session.execute(text("SELECT usesuper FROM pg_user WHERE usename = current_user"))
    ).scalar_one()
    assert is_super is False


async def test_the_owner_role_is_not_a_superuser(owner_session) -> None:
    is_super = (
        await owner_session.execute(
            text("SELECT usesuper FROM pg_user WHERE usename = current_user")
        )
    ).scalar_one()
    assert is_super is False
