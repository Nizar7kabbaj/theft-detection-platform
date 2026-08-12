from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


class DatabaseCredentialError(RuntimeError):
    pass


@lru_cache(maxsize=8)
def _load_password(path: Path) -> str:
    try:
        password = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise DatabaseCredentialError(f"postgres password file missing at {path}") from exc
    except OSError as exc:
        raise DatabaseCredentialError(f"postgres password file unreadable at {path}") from exc
    if not password:
        raise DatabaseCredentialError(f"postgres password file empty at {path}")
    return password


def _build_url(user: str, password: str) -> str:
    settings = get_settings()
    return (
        f"postgresql+asyncpg://{quote_plus(user)}:{quote_plus(password)}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )


def resolve_app_url() -> str:
    settings = get_settings()
    return _build_url(
        settings.postgres_app_user, _load_password(settings.postgres_app_password_file)
    )


def resolve_owner_url() -> str:
    settings = get_settings()
    return _build_url(
        settings.postgres_owner_user,
        _load_password(settings.postgres_owner_password_file),
    )


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            resolve_app_url(),
            pool_size=5,
            max_overflow=5,
            pool_pre_ping=True,
            echo=False,
            connect_args={"server_settings": {"application_name": settings.service_name}},
        )
        logger.info("postgres engine created")
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            autoflush=False,
        )
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    factory = get_sessionmaker()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        logger.info("postgres engine disposed")
