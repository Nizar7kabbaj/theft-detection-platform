from __future__ import annotations

import asyncio
import logging
import secrets
import time
from collections.abc import Callable, Coroutine
from typing import Any
from urllib.parse import urlsplit

from fastapi import WebSocket, WebSocketException, status

from app.core.authz import (
    Permission,
    TokenMissingError,
    TokenRejectedError,
    _resolve_permissions,
    build_auth_client,
    extract_token,
    verify_connection,
)
from app.core.database import get_database
from app.core.errors import AuthUnavailableError
from app.grpc_gen import audit_pb2
from app.schemas.identity import CurrentUser
from app.services.audit_service import AuditClient

logger = logging.getLogger(__name__)

_POLICY = status.WS_1008_POLICY_VIOLATION
_INTERNAL = status.WS_1011_INTERNAL_ERROR
_DEFAULT_PORTS = {"http": 80, "https": 443}
_JITTER_STEPS = 100
_JITTER_FLOOR = 90


def _normalize_origin(value: str) -> str | None:
    parsed = urlsplit(value.strip())
    if parsed.scheme not in _DEFAULT_PORTS or not parsed.hostname:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    host = parsed.hostname.lower()
    if port is None or port == _DEFAULT_PORTS[parsed.scheme]:
        return f"{parsed.scheme}://{host}"
    return f"{parsed.scheme}://{host}:{port}"


def _allowed_origins() -> frozenset[str]:
    from app.core.config import settings

    normalized = (
        _normalize_origin(item) for item in settings.WS_ALLOWED_ORIGINS.split(",") if item.strip()
    )
    return frozenset(item for item in normalized if item is not None)


def check_origin(ws: WebSocket) -> None:
    origin = ws.headers.get("origin")
    if origin is None:
        logger.info("websocket upgrade refused, no origin header")
        raise WebSocketException(code=_POLICY, reason="origin not allowed")
    candidate = _normalize_origin(origin)
    if candidate is None or candidate not in _allowed_origins():
        logger.info("websocket upgrade refused origin=%s", origin)
        raise WebSocketException(code=_POLICY, reason="origin not allowed")


async def authenticate(ws: WebSocket) -> CurrentUser:
    check_origin(ws)
    try:
        token = extract_token(ws)
    except TokenMissingError as exc:
        logger.info("websocket upgrade refused, no credentials")
        raise WebSocketException(code=_POLICY, reason="not authenticated") from exc
    client = build_auth_client(ws)
    try:
        user = await verify_connection(ws, client, token)
    except TokenRejectedError as exc:
        raise WebSocketException(code=_POLICY, reason="not authenticated") from exc
    except AuthUnavailableError as exc:
        logger.warning("websocket upgrade failed, auth service unavailable")
        raise WebSocketException(code=_INTERNAL, reason="auth unavailable") from exc
    return user


def require_ws_permission(
    permission: Permission,
) -> Callable[[WebSocket], Coroutine[Any, Any, CurrentUser]]:
    async def _guard(ws: WebSocket) -> CurrentUser:
        user = await authenticate(ws)
        if permission not in _resolve_permissions(user.roles):
            logger.info(
                "websocket upgrade refused user=%s missing=%s",
                user.username,
                permission.value,
            )
            audit = AuditClient(get_database())
            await audit.emit_authorization_denied(
                subject_id=user.user_id,
                required_permission=permission.value,
                channel=audit_pb2.AUTHORIZATION_CHANNEL_WEBSOCKET,
                method="",
                path=ws.url.path,
                roles=user.roles,
            )
            raise WebSocketException(code=_POLICY, reason="insufficient permission")
        return user

    return _guard


def _next_delay(interval: int) -> float:
    factor = _JITTER_FLOOR + secrets.randbelow(_JITTER_STEPS - _JITTER_FLOOR + 1)
    return interval * factor / _JITTER_STEPS


async def reverify_loop(ws: WebSocket, user: CurrentUser) -> None:
    from app.core.config import settings

    client = build_auth_client(ws)
    grace = settings.WS_REAUTH_GRACE_SECONDS
    last_verified = time.monotonic()

    while True:
        await asyncio.sleep(_next_delay(settings.WS_REAUTH_SECONDS))
        try:
            active = await client.session_active(user.session_id)
        except AuthUnavailableError:
            logger.warning("session recheck failed user=%s, auth unavailable", user.username)
        except Exception:
            logger.exception("session recheck failed user=%s", user.username)
        else:
            if not active:
                logger.info(
                    "websocket closed user=%s, session no longer active",
                    user.username,
                )
                await ws.close(code=_POLICY, reason="session revoked")
                return
            last_verified = time.monotonic()
            continue

        unverified = time.monotonic() - last_verified
        if unverified >= grace:
            logger.warning(
                "websocket closed user=%s, session unverified for %.0fs",
                user.username,
                unverified,
            )
            await ws.close(code=_INTERNAL, reason="session unverified")
            return
