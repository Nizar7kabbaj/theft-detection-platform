from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from app.core import database as database_module
from app.core.config import get_settings
from tests import POSTGRES_APP_PASSWORD_FILE, POSTGRES_OWNER_PASSWORD_FILE

SERVICE_ROOT = Path(__file__).resolve().parents[2]

APP_PASSWORD = POSTGRES_APP_PASSWORD_FILE.read_text(encoding="utf-8").strip()
OWNER_PASSWORD = POSTGRES_OWNER_PASSWORD_FILE.read_text(encoding="utf-8").strip()

BOOTSTRAP = f"""
CREATE ROLE audit_owner LOGIN PASSWORD '{OWNER_PASSWORD}';
CREATE ROLE audit_app LOGIN PASSWORD '{APP_PASSWORD}';
"""

SCHEMA_GRANTS = """
ALTER DATABASE auditdb OWNER TO audit_owner;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO audit_app;
GRANT ALL ON SCHEMA public TO audit_owner;
ALTER SCHEMA public OWNER TO audit_owner;
ALTER DEFAULT PRIVILEGES FOR ROLE audit_owner IN SCHEMA public
  GRANT INSERT, SELECT ON TABLES TO audit_app;
ALTER DEFAULT PRIVILEGES FOR ROLE audit_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO audit_app;
"""


def _exec_sql(container: PostgresContainer, database: str, statement: str) -> None:
    result = container.exec(
        ["psql", "-v", "ON_ERROR_STOP=1", "-U", "harness", "-d", database, "-c", statement]
    )
    if result.exit_code != 0:
        raise RuntimeError(result.output.decode("utf-8", errors="replace"))


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    container = PostgresContainer(
        image="postgres:17-alpine",
        username="harness",
        password="harness-container-password",
        dbname="harnessdb",
        driver="asyncpg",
    )
    container.start()
    try:
        _exec_sql(container, "harnessdb", "CREATE DATABASE auditdb")
        for statement in BOOTSTRAP.strip().split("\n"):
            if statement.strip():
                _exec_sql(container, "harnessdb", statement)
        for statement in SCHEMA_GRANTS.strip().split(";"):
            if statement.strip():
                _exec_sql(container, "auditdb", statement)
        yield container
    finally:
        container.stop()


@pytest.fixture(scope="session")
def database_environment(postgres_container: PostgresContainer) -> Iterator[dict[str, str]]:
    host = postgres_container.get_container_host_ip()
    port = postgres_container.get_exposed_port(5432)
    pinned = {
        "AUDIT_POSTGRES_HOST": host,
        "AUDIT_POSTGRES_PORT": str(port),
        "AUDIT_POSTGRES_DB": "auditdb",
    }
    previous = {name: os.environ.get(name) for name in pinned}
    for name, value in pinned.items():
        os.environ[name] = value
    try:
        yield pinned
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        get_settings.cache_clear()


@pytest.fixture(scope="session")
def migrated(database_environment: dict[str, str]) -> dict[str, str]:
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=SERVICE_ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, **database_environment},
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"alembic failed\n{completed.stdout}\n{completed.stderr}")
    return database_environment


@pytest.fixture
def database_settings(migrated: dict[str, str]) -> Iterator[None]:
    for name, value in migrated.items():
        os.environ[name] = value
    get_settings.cache_clear()
    database_module._load_password.cache_clear()
    yield
    get_settings.cache_clear()


def _engine(url: str):
    return create_async_engine(url, poolclass=None, pool_pre_ping=True)


@pytest_asyncio.fixture
async def owner_engine(database_settings: None) -> AsyncIterator:
    engine = create_async_engine(database_module.resolve_owner_url())
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def app_engine(database_settings: None) -> AsyncIterator:
    engine = create_async_engine(database_module.resolve_app_url())
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def owner_session(owner_engine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(owner_engine, expire_on_commit=False, autoflush=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def app_session(app_engine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(app_engine, expire_on_commit=False, autoflush=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture(autouse=True)
async def clean_tables(database_settings: None) -> AsyncIterator[None]:
    yield
    engine = create_async_engine(database_module.resolve_owner_url())
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "TRUNCATE audit_events, audit_chain_segments, audit_checkpoints "
                    "RESTART IDENTITY"
                )
            )
    finally:
        await engine.dispose()
