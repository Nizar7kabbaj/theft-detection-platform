from __future__ import annotations

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


async def test_the_container_runs_the_expected_postgres(owner_session) -> None:
    version = (await owner_session.execute(text("SHOW server_version"))).scalar_one()
    assert version.startswith("17")


async def test_the_migration_created_the_tables(owner_session) -> None:
    rows = (
        (
            await owner_session.execute(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
                )
            )
        )
        .scalars()
        .all()
    )
    assert "audit_events" in rows
    assert "audit_checkpoints" in rows
    assert "audit_chain_segments" in rows


async def test_the_owner_connects_as_audit_owner(owner_session) -> None:
    assert (await owner_session.execute(text("SELECT current_user"))).scalar_one() == "audit_owner"


async def test_the_app_connects_as_audit_app(app_session) -> None:
    assert (await app_session.execute(text("SELECT current_user"))).scalar_one() == "audit_app"


async def test_the_append_only_triggers_exist(owner_session) -> None:
    rows = (
        (
            await owner_session.execute(
                text("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal ORDER BY tgname")
            )
        )
        .scalars()
        .all()
    )
    assert "trg_audit_events_no_update" in rows
    assert "trg_audit_events_no_delete" in rows
    assert "trg_audit_checkpoints_immutable" in rows
