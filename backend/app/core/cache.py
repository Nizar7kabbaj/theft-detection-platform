import hashlib
import json
from collections.abc import Awaitable, Callable
from typing import Any

from redis.asyncio import Redis


def make_list_key(resource: str, params: dict[str, Any]) -> str:
    payload = json.dumps(params, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"cache:{resource}:list:{digest}"


async def get_or_set(
    redis: Redis,
    key: str,
    ttl: int,
    loader: Callable[[], Awaitable[Any]],
) -> Any:
    raw = await redis.get(key)
    if raw is not None:
        return json.loads(raw)
    value = await loader()
    await redis.set(key, json.dumps(value, separators=(",", ":")), ex=ttl)
    return value


async def invalidate(redis: Redis, key: str) -> None:
    await redis.delete(key)


async def invalidate_prefix(redis: Redis, prefix: str) -> None:
    async for key in redis.scan_iter(match=f"{prefix}*"):
        await redis.delete(key)
