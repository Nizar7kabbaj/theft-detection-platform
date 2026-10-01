import hashlib
import json
import logging
import secrets
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, Request
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.errors import ConflictError, RequestInProgressError
from app.core.redis import get_redis

logger = logging.getLogger(__name__)

HEADER_NAME = "Idempotency-Key"
TTL_SECONDS = 60 * 60 * 24
RETRY_AFTER_SECONDS = 1
_STATE_PENDING = "pending"
_STATE_DONE = "done"
_RELEASE_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


def _encode(document: dict[str, Any]) -> str:
    return json.dumps(document, separators=(",", ":"), sort_keys=True)


@dataclass
class IdempotencyState:
    cached_response: dict[str, Any] | None
    store_key: str | None
    body_hash: str | None
    redis: Redis | None
    claim: str | None = None
    stored: bool = False

    @property
    def is_hit(self) -> bool:
        return self.cached_response is not None

    @property
    def is_tracked(self) -> bool:
        return self.store_key is not None

    async def store(self, response_body: dict[str, Any]) -> None:
        if not self.is_tracked or self.redis is None:
            return
        payload = _encode(
            {"state": _STATE_DONE, "body": response_body, "body_hash": self.body_hash}
        )
        await self.redis.set(self.store_key, payload, ex=TTL_SECONDS)
        self.stored = True

    async def release(self) -> None:
        if self.stored or self.claim is None or self.redis is None:
            return
        script = self.redis.register_script(_RELEASE_LUA)
        try:
            await script(keys=[self.store_key], args=[self.claim])
        except RedisError as exc:
            logger.warning("idempotency claim release failed: %s", exc)


def _hash_body(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _cache_key(method: str, path: str, header_value: str) -> str:
    return f"idem:{method}:{path}:{header_value}"


def _claim_marker(body_hash: str) -> str:
    return _encode(
        {"state": _STATE_PENDING, "body_hash": body_hash, "token": secrets.token_hex(16)}
    )


def _replay(key: str, body_hash: str, raw: bytes | str | None) -> IdempotencyState:
    if raw is None:
        raise RequestInProgressError(RETRY_AFTER_SECONDS)
    stored = json.loads(raw)
    if stored.get("body_hash") != body_hash:
        raise ConflictError("idempotency key reused with different payload")
    if stored.get("state") == _STATE_PENDING:
        raise RequestInProgressError(RETRY_AFTER_SECONDS)
    return IdempotencyState(stored["body"], key, body_hash, None)


async def idempotency(
    request: Request,
    redis: Redis = Depends(get_redis),
) -> AsyncIterator[IdempotencyState]:
    header_value = request.headers.get(HEADER_NAME)
    if not header_value:
        yield IdempotencyState(None, None, None, None)
        return

    body_hash = _hash_body(await request.body())
    key = _cache_key(request.method, request.url.path, header_value)
    claim = _claim_marker(body_hash)

    if await redis.set(key, claim, nx=True, ex=settings.IDEMPOTENCY_PENDING_SECONDS):
        state = IdempotencyState(None, key, body_hash, redis, claim=claim)
        try:
            yield state
        finally:
            await state.release()
        return

    yield _replay(key, body_hash, await redis.get(key))
