from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any
from urllib.parse import urlsplit

from fastapi import WebSocket, WebSocketException, status

from app.core.authz import (
    Permission,
    TokenMissing,
    TokenRejected,
    _resolve_permissions,
    build_auth_client,
    extract_token,
    verify_connection,
)
from app.core.errors import AuthUnavailable
from app.schemas.identity import CurrentUser

logger = logging.getLogger(__name__)

_POLICY = status.WS_1008_POLICY_VIOLATION
_INTERNAL = status.WS_1011_INTERNAL_ERROR
_DEFAULT_PORTS = {"http": 80, "https": 443}


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
        _normalize_origin(item)
        for item in settings.WS_ALLOWED_ORIGINS.split(",")
        if item.strip()
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
    except TokenMissing as exc:
        logger.info("websocket upgrade refused, no credentials")
        raise WebSocketException(code=_POLICY, reason="not authenticated") from exc
    client = build_auth_client(ws)
    try:
        user = await verify_connection(ws, client, token)
    except TokenRejected as exc:
        raise WebSocketException(code=_POLICY, reason="not authenticated") from exc
    except AuthUnavailable as exc:
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
            raise WebSocketException(
                code=_POLICY, reason="insufficient permission"
            )
        return user

    return _guard


async def reverify_loop(ws: WebSocket, user: CurrentUser) -> None:
    from app.core.config import settings

    client = build_auth_client(ws)
    while True:
        await asyncio.sleep(settings.WS_REAUTH_SECONDS)
        try:
            active = await client.session_active(user.session_id)
        except AuthUnavailable:
            logger.warning("session recheck skipped, auth service unavailable")
            continue
        except Exception:
            logger.exception("session recheck failed user=%s", user.username)
            continue
        if not active:
            logger.info(
                "websocket closed user=%s, session no longer active",
                user.username,
            )
            await ws.close(code=_POLICY, reason="session revoked")
            return
