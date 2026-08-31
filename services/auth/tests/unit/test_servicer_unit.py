from __future__ import annotations

from datetime import UTC, datetime

import grpc
import pytest
from redis.exceptions import RedisError

from app.core.tokens import sign_access_token
from app.server import servicer as servicer_module
from app.server.grpc_gen import auth_pb2
from app.server.servicer import AuthServicer
from tests.conftest import FakeAbortError

_USER_ID = "11111111-1111-1111-1111-111111111111"
_SESSION_ID = "22222222-2222-2222-2222-222222222222"


def _token(roles: list[str] | None = None) -> str:
    token, _, _ = sign_access_token(
        user_id=_USER_ID,
        username="operator",
        roles=roles if roles is not None else ["operator"],
        session_id=_SESSION_ID,
    )
    return token


def _not_revoked(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _check(jti: str, session_id: str) -> bool:
        return False

    monkeypatch.setattr(servicer_module, "is_token_revoked", _check)


async def test_valid_token_returns_claims(monkeypatch: pytest.MonkeyPatch, grpc_context):
    _not_revoked(monkeypatch)

    reply = await AuthServicer().VerifyToken(
        auth_pb2.VerifyTokenRequest(token=_token(["operator", "viewer"])), grpc_context
    )

    assert reply.status == auth_pb2.VERIFICATION_STATUS_VALID
    assert reply.user_id == _USER_ID
    assert reply.username == "operator"
    assert list(reply.roles) == ["operator", "viewer"]
    assert reply.session_id == _SESSION_ID


async def test_valid_token_reports_expiry(monkeypatch: pytest.MonkeyPatch, grpc_context):
    _not_revoked(monkeypatch)

    reply = await AuthServicer().VerifyToken(
        auth_pb2.VerifyTokenRequest(token=_token()), grpc_context
    )
    expires_at = reply.expires_at.ToDatetime(tzinfo=UTC)

    assert expires_at > datetime.now(UTC)


async def test_malformed_token_is_reported(grpc_context):
    reply = await AuthServicer().VerifyToken(
        auth_pb2.VerifyTokenRequest(token="not-a-jwt"), grpc_context
    )

    assert reply.status == auth_pb2.VERIFICATION_STATUS_MALFORMED


async def test_empty_token_is_reported_as_malformed(grpc_context):
    reply = await AuthServicer().VerifyToken(auth_pb2.VerifyTokenRequest(token=""), grpc_context)

    assert reply.status == auth_pb2.VERIFICATION_STATUS_MALFORMED


async def test_revocation_check_failure_aborts_unavailable(
    monkeypatch: pytest.MonkeyPatch, grpc_context
):
    async def _boom(jti: str, session_id: str) -> bool:
        raise RedisError("revocation store down")

    monkeypatch.setattr(servicer_module, "is_token_revoked", _boom)

    with pytest.raises(FakeAbortError) as excinfo:
        await AuthServicer().VerifyToken(auth_pb2.VerifyTokenRequest(token=_token()), grpc_context)

    assert excinfo.value.code == grpc.StatusCode.UNAVAILABLE
    assert grpc_context.aborted == [(grpc.StatusCode.UNAVAILABLE, "revocation store unavailable")]


async def test_revoked_token_is_reported(monkeypatch: pytest.MonkeyPatch, grpc_context):
    async def _revoked(jti: str, session_id: str) -> bool:
        return True

    monkeypatch.setattr(servicer_module, "is_token_revoked", _revoked)

    reply = await AuthServicer().VerifyToken(
        auth_pb2.VerifyTokenRequest(token=_token()), grpc_context
    )

    assert reply.status == auth_pb2.VERIFICATION_STATUS_REVOKED


async def test_revocation_check_receives_jti_and_session(
    monkeypatch: pytest.MonkeyPatch, grpc_context
):
    seen: list[tuple[str, str]] = []

    async def _record(jti: str, session_id: str) -> bool:
        seen.append((jti, session_id))
        return False

    monkeypatch.setattr(servicer_module, "is_token_revoked", _record)
    token, jti, _ = sign_access_token(
        user_id=_USER_ID, username="operator", roles=[], session_id=_SESSION_ID
    )

    await AuthServicer().VerifyToken(auth_pb2.VerifyTokenRequest(token=token), grpc_context)

    assert seen == [(jti, _SESSION_ID)]


async def test_every_token_failure_maps_to_a_distinct_status():
    statuses = set(servicer_module._FAILURE_STATUS.values())

    assert len(statuses) == len(servicer_module._FAILURE_STATUS)
    assert auth_pb2.VERIFICATION_STATUS_VALID not in statuses


async def test_abort_stops_execution(grpc_context):
    with pytest.raises(FakeAbortError):
        await grpc_context.abort(grpc.StatusCode.UNAVAILABLE, "halt")
