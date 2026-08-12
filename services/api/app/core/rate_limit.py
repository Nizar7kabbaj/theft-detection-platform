from __future__ import annotations

import logging
import math

from fastapi import Depends
from redis.asyncio import Redis
from redis.commands.core import AsyncScript
from redis.exceptions import RedisError

from app.core.authz import get_current_user
from app.core.config import settings
from app.core.redis import get_redis
from app.schemas.identity import CurrentUser

logger = logging.getLogger(__name__)

_script: AsyncScript | None = None

_GCRA_LUA = """
local key = KEYS[1]
local period = tonumber(ARGV[1])
local burst = tonumber(ARGV[2])

local t = redis.call('TIME')
local now = (tonumber(t[1]) * 1000) + math.floor(tonumber(t[2]) / 1000)

local tat = tonumber(redis.call('get', key) or now)
if tat < now then
    tat = now
end

local allow_at = tat - ((burst - 1) * period)
if now < allow_at then
    return {0, allow_at - now}
end

local new_tat = tat + period
redis.call('set', key, new_tat, 'PX', math.ceil(new_tat - now))
return {1, 0}
"""


class RateLimitedError(Exception):
    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__("rate limit exceeded")


def _register(client: Redis) -> AsyncScript:
    global _script
    if _script is None:
        _script = client.register_script(_GCRA_LUA)
    return _script


def _rate_key(user_id: str) -> str:
    return f"rl:{user_id}"


def _ws_rate_key(user_id: str) -> str:
    return f"rl:ws:{user_id}"


async def check_ws_upgrade(client: Redis, user_id: str) -> bool:
    if not settings.RATE_LIMIT_ENABLED:
        return True
    try:
        script = _register(client)
        period_ms = (settings.WS_RATE_WINDOW_SECONDS * 1000) / settings.WS_RATE_UPGRADES
        result = await script(
            keys=[_ws_rate_key(user_id)],
            args=[period_ms, settings.WS_RATE_BURST],
        )
    except RedisError:
        logger.warning("websocket rate limit skipped on redis error user=%s", user_id)
        return True
    return bool(int(result[0]))


async def _check(client: Redis, user_id: str) -> tuple[bool, int]:
    script = _register(client)
    period_ms = (settings.RATE_LIMIT_WINDOW_SECONDS * 1000) / settings.RATE_LIMIT_REQUESTS
    result = await script(
        keys=[_rate_key(user_id)],
        args=[period_ms, settings.RATE_LIMIT_BURST],
    )
    allowed = bool(int(result[0]))
    retry_ms = int(result[1])
    return allowed, retry_ms


async def rate_limit(
    user: CurrentUser = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> None:
    if not settings.RATE_LIMIT_ENABLED:
        return
    try:
        allowed, retry_ms = await _check(redis, user.user_id)
    except RedisError:
        logger.warning("rate limit skipped on redis error user=%s", user.user_id)
        return
    if not allowed:
        retry_after = max(1, math.ceil(retry_ms / 1000))
        logger.info("rate limit hit user=%s retry_after=%ss", user.user_id, retry_after)
        raise RateLimitedError(retry_after)
