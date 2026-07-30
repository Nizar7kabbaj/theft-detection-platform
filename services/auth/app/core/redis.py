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


async def revoke_jti(jti: str, ttl_seconds: int) -> None:
    await get_redis().set(f"revoked:jti:{jti}", 1, ex=ttl_seconds)


async def is_revoked(jti: str) -> bool:
    return await get_redis().exists(f"revoked:jti:{jti}") == 1


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
        logger.info("redis client closed")
