from __future__ import annotations

import logging
import time
from functools import lru_cache

from redis.asyncio import Redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_client: Redis | None = None


class RedisCredentialError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _load_redis_password() -> str:
    path = get_settings().redis_password_file
    try:
        password = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise RedisCredentialError(f"redis password file missing at {path}") from exc
    except OSError as exc:
        raise RedisCredentialError(f"redis password file unreadable at {path}") from exc
    if not password:
        raise RedisCredentialError(f"redis password file empty at {path}")
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
            socket_connect_timeout=settings.redis_connect_timeout_seconds,
            socket_timeout=settings.redis_socket_timeout_seconds,
        )
        logger.info("redis client created")
    return _client


def rate_limit_key(source_service: int, window: int) -> str:
    return f"audit:rl:{source_service}:{window}"


async def check_append_rate(source_service: int) -> bool:
    settings = get_settings()
    span = max(settings.append_rate_window_seconds, 1)
    window = int(time.time()) // span
    key = rate_limit_key(source_service, window)
    client = get_redis()
    try:
        count = await client.incr(key)
        if count == 1:
            await client.pexpire(key, span * 2000)
        return count <= settings.append_rate_limit
    except Exception as exc:
        logger.error("rate limit check failed: %s", exc)
        return not get_settings().append_rate_fail_closed
    

async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
        logger.info("redis client closed")
