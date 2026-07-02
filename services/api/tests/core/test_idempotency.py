from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest

from app.core.errors import ConflictError
from app.core.idempotency import (
    HEADER_NAME,
    TTL_SECONDS,
    IdempotencyState,
    _cache_key,
    _hash_body,
    idempotency,
)


def test_hash_body_is_deterministic_sha256() -> None:
    payload = b'{"alert_id":"a1"}'
    h1 = _hash_body(payload)
    h2 = _hash_body(payload)
    assert h1 == h2
    assert h1 == hashlib.sha256(payload).hexdigest()
    assert len(h1) == 64


def test_hash_body_differs_for_different_bodies() -> None:
    assert _hash_body(b"a") != _hash_body(b"b")


def test_cache_key_format() -> None:
    key = _cache_key("POST", "/api/v1/alerts", "abc-123")
    assert key == "idem:POST:/api/v1/alerts:abc-123"


def test_state_properties_reflect_fields() -> None:
    miss = IdempotencyState(None, "k", "h", redis=object())
    hit = IdempotencyState({"alert_id": "a1"}, "k", "h", redis=object())
    inert = IdempotencyState(None, None, None, None)

    assert miss.is_tracked is True
    assert miss.is_hit is False
    assert hit.is_tracked is True
    assert hit.is_hit is True
    assert inert.is_tracked is False
    assert inert.is_hit is False


async def test_store_is_noop_when_not_tracked(mocker) -> None:
    redis = mocker.AsyncMock()
    state = IdempotencyState(None, None, None, redis)
    await state.store({"alert_id": "a1"})
    redis.set.assert_not_called()


async def test_store_writes_envelope_with_ttl(mocker) -> None:
    redis = mocker.AsyncMock()
    state = IdempotencyState(None, "idem:POST:/x:k1", "bodyhash", redis)
    body = {"alert_id": "a1", "severity": "SEVERITY_WARNING"}

    await state.store(body)

    redis.set.assert_awaited_once()
    args, kwargs = redis.set.call_args
    assert args[0] == "idem:POST:/x:k1"
    stored = json.loads(args[1])
    assert stored == {"body": body, "body_hash": "bodyhash"}
    assert kwargs["ex"] == TTL_SECONDS


async def test_dependency_returns_inert_state_without_header(mocker) -> None:
    request = SimpleNamespace(
        headers={},
        method="POST",
        url=SimpleNamespace(path="/api/v1/alerts"),
        body=mocker.AsyncMock(),
    )
    redis = mocker.AsyncMock()

    state = await idempotency(request, redis)

    assert state.is_hit is False
    assert state.is_tracked is False
    request.body.assert_not_called()
    redis.get.assert_not_called()


async def test_dependency_raises_conflict_on_payload_mismatch(mocker) -> None:
    body = b'{"alert_id":"a1"}'
    stored_payload = json.dumps({"body": {"x": 1}, "body_hash": "different"})
    request = SimpleNamespace(
        headers={HEADER_NAME: "k1"},
        method="POST",
        url=SimpleNamespace(path="/api/v1/alerts"),
        body=mocker.AsyncMock(return_value=body),
    )
    redis = mocker.AsyncMock()
    redis.get.return_value = stored_payload

    with pytest.raises(ConflictError, match="different payload"):
        await idempotency(request, redis)
