from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

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


def _allowed_origins() -> frozenset[str]:
    from app.core.config import settings

    return frozenset(
        item.strip()
        for item in settings.WS_ALLOWED_ORIGINS.split(",")
        if item.strip()
    )


def check_origin(ws: WebSocket) -> None:
    origin = ws.headers.get("origin")
    if origin is None:
        logger.info("websocket upgrade refused, no origin header")
        raise WebSocketException(code=_POLICY, reason="origin not allowed")
    if origin not in _allowed_origins():
        logger.info("websocket upgrade refused origin=%s", origin)
        raise WebSocketException(code=_POLICY, reason="origin not allowed")


async def authenticate(ws: WebSocket) -> tuple[CurrentUser, str]:
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
    return user, token


def require_ws_permission(
    permission: Permission,
) -> Callable[[WebSocket], Coroutine[Any, Any, tuple[CurrentUser, str]]]:
    async def _guard(ws: WebSocket) -> tuple[CurrentUser, str]:
        user, token = await authenticate(ws)
        if permission not in _resolve_permissions(user.roles):
            logger.info(
                "websocket upgrade refused user=%s missing=%s",
                user.username,
                permission.value,
            )
            raise WebSocketException(
                code=_POLICY, reason="insufficient permission"
            )
        return user, token

    return _guard


async def reverify_loop(ws: WebSocket, token: str) -> None:
    from app.core.config import settings

    client = build_auth_client(ws)
    while True:
        await asyncio.sleep(settings.WS_REAUTH_SECONDS)
        try:
            await verify_connection(ws, client, token)
        except TokenRejected:
            logger.info("websocket closed, session no longer valid")
            await ws.close(code=_POLICY, reason="session revoked")
            return
        except AuthUnavailable:
            logger.warning("session recheck skipped, auth service unavailable")
