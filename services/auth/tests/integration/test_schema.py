from __future__ import annotations

from sqlalchemy import text

_EXPECTED_TABLES = {
    "alembic_version",
    "audit_outbox",
    "audit_outbox_dead",
    "refresh_tokens",
    "sessions",
    "users",
}


async def test_migrations_created_every_table(db_session):
    result = await db_session.execute(
        text("select tablename from pg_tables where schemaname = 'public'")
    )
    tables = {row[0] for row in result.all()}

    assert tables >= _EXPECTED_TABLES


async def test_migration_head_is_recorded(db_session):
    result = await db_session.execute(text("select version_num from alembic_version"))

    assert result.scalar_one() == "a3f1c8d24e07"


async def test_gen_random_uuid_is_available(db_session):
    result = await db_session.execute(text("select gen_random_uuid()"))

    assert result.scalar_one()


async def test_truncate_leaves_tables_empty(db_session):
    result = await db_session.execute(text("select count(*) from users"))

    assert result.scalar_one() == 0
