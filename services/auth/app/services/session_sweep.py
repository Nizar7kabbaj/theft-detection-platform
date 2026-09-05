from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime, timedelta

from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.database import get_sessionmaker
from app.core.redis import revoke_sid
from app.repositories.session_repository import SessionRepository

logger = logging.getLogger(__name__)

_MAX_PER_CYCLE = 500


async def _sweep_once() -> int:
    settings = get_settings()
    cutoff = datetime.now(UTC) - timedelta(seconds=settings.session_idle_timeout_seconds)
    factory = get_sessionmaker()
    async with factory() as db:
        sessions = SessionRepository(db)
        idle = await sessions.idle_ids(cutoff)
        if not idle:
            await db.rollback()
            return 0
        batch = idle[:_MAX_PER_CYCLE]
        revoked = await sessions.revoke_ids(batch)
        await db.commit()
    for session_id in batch:
        try:
            await revoke_sid(session_id, settings.access_token_ttl_seconds)
        except RedisError:
            logger.warning("idle session revoked in store but not in cache, id=%s", session_id)
    return revoked


async def run_session_sweep(stop_event: asyncio.Event) -> None:
    logger.info("session sweep started")
    interval = get_settings().session_sweep_interval_seconds
    while not stop_event.is_set():
        try:
            revoked = await _sweep_once()
        except SQLAlchemyError:
            logger.warning("session sweep paused, session store unavailable")
            revoked = 0
        except Exception:
            logger.exception("session sweep cycle failed")
            revoked = 0
        if revoked > 0:
            logger.info("revoked %d idle sessions", revoked)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
    logger.info("session sweep stopped")
