import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, Request
from redis.asyncio import Redis

from .errors import ConflictError
from .redis import get_redis

logger = logging.getLogger(__name__)

HEADER_NAME = "Idempotency-Key"
TTL_SECONDS = 60 * 60 * 24


@dataclass
class IdempotencyState:
    cached_response: dict[str, Any] | None
    store_key: str | None
    body_hash: str | None
    redis: Redis | None

    @property
    def is_hit(self) -> bool:
        return self.cached_response is not None

    @property
    def is_tracked(self) -> bool:
        return self.store_key is not None

    async def store(self, response_body: dict[str, Any]) -> None:
        if not self.is_tracked or self.redis is None:
            return
        payload = json.dumps(
            {"body": response_body, "body_hash": self.body_hash},
            separators=(",", ":"),
            sort_keys=True,
        )
        await self.redis.set(self.store_key, payload, ex=TTL_SECONDS)


def _hash_body(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _cache_key(method: str, path: str, header_value: str) -> str:
    return f"idem:{method}:{path}:{header_value}"


async def idempotency(
    request: Request,
    redis: Redis = Depends(get_redis),
) -> IdempotencyState:
    header_value = request.headers.get(HEADER_NAME)
    if not header_value:
        return IdempotencyState(None, None, None, None)

    body = await request.body()
    body_hash = _hash_body(body)
    key = _cache_key(request.method, request.url.path, header_value)

    raw = await redis.get(key)
    if raw is None:
        return IdempotencyState(None, key, body_hash, redis)

    stored = json.loads(raw)
    if stored.get("body_hash") != body_hash:
        raise ConflictError("idempotency key reused with different payload")
    return IdempotencyState(stored["body"], key, body_hash, redis)
