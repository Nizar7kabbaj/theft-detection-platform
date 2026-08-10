from __future__ import annotations

import logging
from functools import lru_cache

from redis.asyncio import Redis
from redis.commands.core import AsyncScript

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_client: Redis | None = None
_check_script: AsyncScript | None = None
_record_script: AsyncScript | None = None

_CHECK_LUA = """
local count = tonumber(redis.call('get', KEYS[1]) or '0')
local limit = tonumber(ARGV[1])
if count >= limit then
    local ttl = redis.call('pttl', KEYS[1])
    if ttl < 0 then
        ttl = 0
    end
    return {1, ttl}
end
return {0, 0}
"""

_RECORD_LUA = """
local limit = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local block_ms = tonumber(ARGV[3])
local count = redis.call('incr', KEYS[1])
if count == 1 then
    redis.call('pexpire', KEYS[1], window_ms)
end
if count == limit then
    redis.call('pexpire', KEYS[1], block_ms)
    return {1, count}
end
if count > limit then
    redis.call('pexpire', KEYS[1], block_ms)
    return {0, count}
end
return {0, count}
"""


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


def _register_scripts() -> tuple[AsyncScript, AsyncScript]:
    global _check_script, _record_script
    if _check_script is None or _record_script is None:
        client = get_redis()
        _check_script = client.register_script(_CHECK_LUA)
        _record_script = client.register_script(_RECORD_LUA)
    return _check_script, _record_script


def login_key(ip: str, username: str) -> str:
    return f"login:fail:{ip}:{username}"


async def check_login(ip: str, username: str) -> tuple[bool, int]:
    check, _ = _register_scripts()
    settings = get_settings()
    result = await check(
        keys=[login_key(ip, username)],
        args=[settings.login_max_attempts],
    )
    locked = bool(int(result[0]))
    retry_ms = int(result[1])
    return locked, retry_ms


async def record_failure(ip: str, username: str) -> tuple[bool, int]:
    _, record = _register_scripts()
    settings = get_settings()
    result = await record(
        keys=[login_key(ip, username)],
        args=[
            settings.login_max_attempts,
            settings.login_window_seconds * 1000,
            settings.login_block_seconds * 1000,
        ],
    )
    return bool(int(result[0])), int(result[1])


async def reset_failures(ip: str, username: str) -> None:
    await get_redis().delete(login_key(ip, username))


async def revoke_jti(jti: str, ttl_seconds: int) -> None:
    await get_redis().set(f"revoked:jti:{jti}", 1, ex=ttl_seconds)


async def revoke_sid(session_id: str, ttl_seconds: int) -> None:
    await get_redis().set(f"revoked:sid:{session_id}", 1, ex=ttl_seconds)


async def is_token_revoked(jti: str, session_id: str) -> bool:
    return await get_redis().exists(f"revoked:jti:{jti}", f"revoked:sid:{session_id}") > 0


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
        logger.info("redis client closed")
