from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from tests import (
    POSTGRES_APP_PASSWORD_FILE,
    POSTGRES_OWNER_PASSWORD_FILE,
    REDIS_PASSWORD_FILE,
)

_POSTGRES_IMAGE = "postgres:17-alpine"
_REDIS_IMAGE = "redis:7-alpine"
_ROLE = "authtest"
_DATABASE = "authdb"
_REDIS_USER = "auth"
_REDIS_PASSWORD = "harness-redis-password"
_DEFAULT_REDIS_PASSWORD = "harness-default-password"
_TABLES = (
    "audit_outbox_dead",
    "audit_outbox",
    "refresh_tokens",
    "sessions",
    "users",
)


def _service_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _run_migrations(env: dict[str, str]) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=_service_root(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"alembic upgrade failed\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    container = PostgresContainer(
        image=_POSTGRES_IMAGE,
        username=_ROLE,
        password="harness-postgres-password",
        dbname=_DATABASE,
        driver="asyncpg",
    )
    container.start()
    try:
        yield container
    finally:
        container.stop()


@pytest.fixture(scope="session", autouse=True)
def postgres_env(postgres_container: PostgresContainer) -> None:
    password = postgres_container.password
    POSTGRES_APP_PASSWORD_FILE.write_text(password, encoding="utf-8")
    POSTGRES_OWNER_PASSWORD_FILE.write_text(password, encoding="utf-8")

    os.environ["AUTH_POSTGRES_HOST"] = postgres_container.get_container_host_ip()
    os.environ["AUTH_POSTGRES_PORT"] = str(postgres_container.get_exposed_port(5432))
    os.environ["AUTH_POSTGRES_DB"] = _DATABASE
    os.environ["AUTH_POSTGRES_APP_USER"] = _ROLE
    os.environ["AUTH_POSTGRES_OWNER_USER"] = _ROLE

    from app.core.config import get_settings

    get_settings.cache_clear()
    _run_migrations(dict(os.environ))


@pytest.fixture(scope="session")
def redis_container() -> Iterator[RedisContainer]:
    container = RedisContainer(image=_REDIS_IMAGE, password=_DEFAULT_REDIS_PASSWORD)
    container.start()
    try:
        client = container.get_client()
        client.execute_command(
            "ACL",
            "SETUSER",
            _REDIS_USER,
            "on",
            f">{_REDIS_PASSWORD}",
            "~login:fail:*",
            "~revoked:*",
            "&session:revoked",
            "+@read",
            "+@write",
            "+@scripting",
            "+@pubsub",
            "+@connection",
        )
        client.close()
        yield container
    finally:
        container.stop()


@pytest.fixture(scope="session", autouse=True)
def redis_env(redis_container: RedisContainer) -> None:
    REDIS_PASSWORD_FILE.write_text(_REDIS_PASSWORD, encoding="utf-8")
    os.environ["AUTH_REDIS_HOST"] = redis_container.get_container_host_ip()
    os.environ["AUTH_REDIS_PORT"] = str(redis_container.get_exposed_port(6379))
    os.environ["AUTH_REDIS_USER"] = _REDIS_USER
    os.environ["AUTH_REDIS_TLS"] = "false"


@pytest.fixture
async def redis_client(redis_container: RedisContainer) -> AsyncIterator:
    from app.core import redis as redis_module

    client = redis_module.get_redis()
    await client.flushdb()
    try:
        yield client
    finally:
        await client.flushdb()
        await redis_module.close_redis()
        redis_module._check_script = None
        redis_module._record_script = None


@pytest.fixture
async def db_engine():
    from app.core.config import get_settings
    from app.core.database import resolve_app_url

    get_settings.cache_clear()
    engine = create_async_engine(resolve_app_url(), poolclass=None)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture(autouse=True)
async def clean_tables(db_engine) -> None:
    statement = text(f"truncate table {', '.join(_TABLES)} restart identity cascade")
    async with db_engine.begin() as connection:
        await connection.execute(statement)


@pytest.fixture
async def db_session(db_engine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(bind=db_engine, expire_on_commit=False, autoflush=False)
    async with factory() as session:
        yield session
