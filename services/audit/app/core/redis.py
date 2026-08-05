from __future__ import annotations

import logging
from functools import lru_cache

from redis.asyncio import Redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_client: Redis | None = None


@lru_cache(maxsize=1)
def _load_redis_password() -> str:
    path = get_settings().redis_password_file
    try:
        password = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        logger.error("redis password file missing at %s", path)
        return ""
    except OSError as exc:
        logger.error("redis password file unreadable at %s: %s", path, exc)
        return ""
    if not password:
        logger.error("redis password file empty at %s", path)
    return password


def get_redis() -> Redis:
    global _client
    if _client is None:
        settings = get_settings()
        _client = Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            username=settings.redis_user,
            password=_load_redis_password(),
            db=settings.redis_db,
            decode_responses=True,
            health_check_interval=30,
        )
        logger.info("redis client created")
    return _client


def rate_limit_key(source_service: str) -> str:
    return f"audit:rl:{source_service or 'unknown'}"


async def check_append_rate(source_service: str) -> bool:
    settings = get_settings()
    key = rate_limit_key(source_service)
    client = get_redis()
    try:
        count = await client.incr(key)
        if count == 1:
            await client.pexpire(key, settings.append_rate_window_seconds * 1000)
        return count <= settings.append_rate_limit
    except Exception as exc:
        logger.error("rate limit check failed for %s: %s", source_service, exc)
        return True


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
        logger.info("redis client closed")
