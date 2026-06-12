from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.broadcast_service import BroadcastService

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_broadcaster(ws: WebSocket) -> BroadcastService:
    return ws.app.state.broadcaster


async def _serve(ws: WebSocket, topic: str) -> None:
    await ws.accept()
    broadcaster = _get_broadcaster(ws)
    registered = await broadcaster.register(ws, topic)
    if not registered:
        return
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("websocket loop error topic=%s: %s", topic, exc)
    finally:
        broadcaster.unregister(ws, topic)


@router.websocket("/ws/alerts")
async def alerts_stream(ws: WebSocket) -> None:
    await _serve(ws, "alerts")


@router.websocket("/ws/cameras")
async def cameras_stream(ws: WebSocket) -> None:
    await _serve(ws, "cameras")
