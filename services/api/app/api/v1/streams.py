from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.core.authz import Permission
from app.core.ws_authz import require_ws_permission, reverify_loop
from app.schemas.identity import CurrentUser
from app.services.broadcast_service import BroadcastService

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_broadcaster(ws: WebSocket) -> BroadcastService:
    return ws.app.state.broadcaster


async def _serve(ws: WebSocket, topic: str, token: str) -> None:
    await ws.accept()
    broadcaster = _get_broadcaster(ws)
    registered = await broadcaster.register(ws, topic)
    if not registered:
        return
    watchdog = asyncio.create_task(reverify_loop(ws, token))
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("websocket loop error topic=%s: %s", topic, exc)
    finally:
        watchdog.cancel()
        broadcaster.unregister(ws, topic)


@router.websocket("/ws/alerts")
async def alerts_stream(
    ws: WebSocket,
    identity: tuple[CurrentUser, str] = Depends(
        require_ws_permission(Permission.ALERT_READ)
    ),
) -> None:
    await _serve(ws, "alerts", identity[1])


@router.websocket("/ws/cameras")
async def cameras_stream(
    ws: WebSocket,
    identity: tuple[CurrentUser, str] = Depends(
        require_ws_permission(Permission.CAMERA_READ)
    ),
) -> None:
    await _serve(ws, "cameras", identity[1])
