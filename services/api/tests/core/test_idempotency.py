from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.core.errors import ConflictError, RequestInProgressError
from app.core.idempotency import (
    HEADER_NAME,
    TTL_SECONDS,
    IdempotencyState,
    _cache_key,
    _hash_body,
    idempotency,
)

_BODY = b'{"alert_id":"a1"}'
_KEY = "idem:POST:/api/v1/alerts:k1"


def _request(mocker, header: str | None = "k1", body: bytes = _BODY) -> SimpleNamespace:
    return SimpleNamespace(
        headers={HEADER_NAME: header} if header else {},
        method="POST",
        url=SimpleNamespace(path="/api/v1/alerts"),
        body=mocker.AsyncMock(return_value=body),
    )


def _redis(mocker, claimed: bool | None, existing: str | None = None):
    redis = mocker.AsyncMock()
    redis.set.return_value = claimed
    redis.get.return_value = existing
    script = mocker.AsyncMock(return_value=1)
    redis.register_script = mocker.Mock(return_value=script)
    return redis, script


def test_hash_body_is_deterministic_sha256() -> None:
    h1 = _hash_body(_BODY)
    assert h1 == _hash_body(_BODY)
    assert h1 == hashlib.sha256(_BODY).hexdigest()
    assert len(h1) == 64


def test_hash_body_differs_for_different_bodies() -> None:
    assert _hash_body(b"a") != _hash_body(b"b")


def test_cache_key_format() -> None:
    assert _cache_key("POST", "/api/v1/alerts", "abc-123") == "idem:POST:/api/v1/alerts:abc-123"


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


async def test_store_writes_done_envelope_with_ttl(mocker) -> None:
    redis = mocker.AsyncMock()
    state = IdempotencyState(None, "idem:POST:/x:k1", "bodyhash", redis)
    body = {"alert_id": "a1", "severity": "SEVERITY_WARNING"}

    await state.store(body)

    args, kwargs = redis.set.call_args
    assert args[0] == "idem:POST:/x:k1"
    assert json.loads(args[1]) == {"state": "done", "body": body, "body_hash": "bodyhash"}
    assert kwargs["ex"] == TTL_SECONDS
    assert state.stored is True


async def test_no_header_yields_inert_state(mocker) -> None:
    request = _request(mocker, header=None)
    redis, _ = _redis(mocker, claimed=True)

    gen = idempotency(request, redis)
    state = await anext(gen)
    await gen.aclose()

    assert state.is_tracked is False
    request.body.assert_not_called()
    redis.set.assert_not_called()


async def test_first_request_claims_key_atomically(mocker) -> None:
    redis, _ = _redis(mocker, claimed=True)

    gen = idempotency(_request(mocker), redis)
    state = await anext(gen)

    assert state.is_tracked is True
    assert state.is_hit is False
    args, kwargs = redis.set.call_args
    assert args[0] == _KEY
    assert json.loads(args[1])["state"] == "pending"
    assert kwargs == {"nx": True, "ex": settings.IDEMPOTENCY_PENDING_SECONDS}
    await gen.aclose()


async def test_claim_kept_after_store(mocker) -> None:
    redis, script = _redis(mocker, claimed=True)

    gen = idempotency(_request(mocker), redis)
    state = await anext(gen)
    await state.store({"alert_id": "a1"})
    with pytest.raises(StopAsyncIteration):
        await anext(gen)

    script.assert_not_awaited()


async def test_claim_released_when_handler_fails(mocker) -> None:
    redis, script = _redis(mocker, claimed=True)

    gen = idempotency(_request(mocker), redis)
    state = await anext(gen)
    with pytest.raises(RuntimeError):
        await gen.athrow(RuntimeError("handler failed"))

    script.assert_awaited_once_with(keys=[_KEY], args=[state.claim])


async def test_pending_claim_reports_in_progress(mocker) -> None:
    pending = json.dumps({"state": "pending", "body_hash": _hash_body(_BODY), "token": "t"})
    redis, _ = _redis(mocker, claimed=None, existing=pending)

    with pytest.raises(RequestInProgressError):
        await anext(idempotency(_request(mocker), redis))


async def test_vanished_claim_reports_in_progress(mocker) -> None:
    redis, _ = _redis(mocker, claimed=None, existing=None)

    with pytest.raises(RequestInProgressError):
        await anext(idempotency(_request(mocker), redis))


async def test_payload_mismatch_raises_conflict(mocker) -> None:
    stored = json.dumps({"state": "done", "body": {"x": 1}, "body_hash": "different"})
    redis, _ = _redis(mocker, claimed=None, existing=stored)

    with pytest.raises(ConflictError, match="different payload"):
        await anext(idempotency(_request(mocker), redis))


async def test_done_entry_replays_response(mocker) -> None:
    body = {"alert_id": "a1"}
    stored = json.dumps({"state": "done", "body": body, "body_hash": _hash_body(_BODY)})
    redis, _ = _redis(mocker, claimed=None, existing=stored)

    state = await anext(idempotency(_request(mocker), redis))

    assert state.is_hit is True
    assert state.cached_response == body


async def test_entry_without_state_replays_response(mocker) -> None:
    body = {"alert_id": "a1"}
    stored = json.dumps({"body": body, "body_hash": _hash_body(_BODY)})
    redis, _ = _redis(mocker, claimed=None, existing=stored)

    state = await anext(idempotency(_request(mocker), redis))

    assert state.cached_response == body
