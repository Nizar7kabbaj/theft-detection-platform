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


@lru_cache(maxsize=8)
def _load_password(path: Path) -> str:
    try:
        password = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        logger.error("postgres password file missing at %s", path)
        return ""
    except OSError as exc:
        logger.error("postgres password file unreadable at %s: %s", path, exc)
        return ""
    if not password:
        logger.error("postgres password file empty at %s", path)
    return password


def _build_url(user: str, password: str) -> str:
    settings = get_settings()
    return (
        f"postgresql+asyncpg://{quote_plus(user)}:{quote_plus(password)}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )


def resolve_app_url() -> str:
    settings = get_settings()
    password = _load_password(settings.postgres_app_password_file)
    return _build_url(settings.postgres_app_user, password)


def resolve_owner_url() -> str:
    settings = get_settings()
    password = _load_password(settings.postgres_owner_password_file)
    return _build_url(settings.postgres_owner_user, password)


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            resolve_app_url(),
            pool_size=5,
            max_overflow=5,
            pool_pre_ping=True,
            echo=False,
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
