from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from redis.asyncio import Redis

from app.core.authz import Permission
from app.core.database import get_database
from app.core.ws_authz import require_ws_permission, reverify_loop
from app.schemas.identity import CurrentUser
from app.services.broadcast_service import BroadcastService
from app.services.frame_stream import ViewerLimit, run_frame_pump
from app.services.revocation_service import RevocationService

logger = logging.getLogger(__name__)
router = APIRouter()
_POLICY = 1008


def _get_broadcaster(ws: WebSocket) -> BroadcastService:
    return ws.app.state.broadcaster


def _get_revocations(ws: WebSocket) -> RevocationService:
    return ws.app.state.revocations


async def _reader(ws: WebSocket) -> None:
    while True:
        await ws.receive_text()


async def _serve(ws: WebSocket, topic: str, user: CurrentUser, permission: Permission) -> None:
    await ws.accept()
    broadcaster = _get_broadcaster(ws)
    registered = await broadcaster.register(ws, topic)
    if not registered:
        return
    revocations = _get_revocations(ws)
    revoked = revocations.register(user.session_id)
    watchdog = asyncio.create_task(reverify_loop(ws, user, permission))
    reader = asyncio.create_task(_reader(ws))
    pushed = asyncio.create_task(revoked.wait(), name="revocation-wait")
    tasks = (watchdog, reader, pushed)
    try:
        done, pending = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        if pushed in done:
            logger.info("websocket closed user=%s, session revoked", user.username)
            await ws.close(code=_POLICY, reason="session revoked")
            return
        for task in done:
            exc = task.exception()
            if exc is None or isinstance(exc, WebSocketDisconnect):
                continue
            logger.warning("websocket task ended topic=%s: %s", topic, exc)
            await ws.close(code=1011, reason="stream error")
    finally:
        for task in tasks:
            task.cancel()
        revocations.unregister(user.session_id, revoked)
        broadcaster.unregister(ws, topic)


@router.websocket("/ws/alerts")
async def alerts_stream(
    ws: WebSocket,
    user: CurrentUser = Depends(require_ws_permission(Permission.ALERT_READ)),
) -> None:
    await _serve(ws, "alerts", user, Permission.ALERT_READ)


@router.websocket("/ws/cameras")
async def cameras_stream(
    ws: WebSocket,
    user: CurrentUser = Depends(require_ws_permission(Permission.CAMERA_READ)),
) -> None:
    await _serve(ws, "cameras", user, Permission.CAMERA_READ)


def _get_stream_redis(ws: WebSocket) -> Redis:
    return ws.app.state.stream_redis


def _get_frame_viewers(ws: WebSocket) -> ViewerLimit:
    return ws.app.state.frame_viewers


async def _camera_exists(camera_id: str) -> bool:
    doc = await get_database().cameras.find_one({"camera_id": camera_id}, {"_id": 1})
    return doc is not None


async def _stream_frames(ws: WebSocket, camera_id: str, user: CurrentUser) -> None:
    await ws.accept()
    revocations = _get_revocations(ws)
    revoked = revocations.register(user.session_id)
    watchdog = asyncio.create_task(reverify_loop(ws, user, Permission.CAMERA_READ))
    reader = asyncio.create_task(_reader(ws))
    pushed = asyncio.create_task(revoked.wait(), name="revocation-wait")
    pump = asyncio.create_task(run_frame_pump(ws, _get_stream_redis(ws), camera_id))
    tasks = (watchdog, reader, pushed, pump)
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        if pushed in done:
            await ws.close(code=_POLICY, reason="session revoked")
            return
        for task in done:
            exc = task.exception()
            if exc is None or isinstance(exc, WebSocketDisconnect):
                continue
            logger.warning("frame stream ended camera=%s: %s", camera_id, exc)
            await ws.close(code=1011, reason="stream error")
    finally:
        for task in tasks:
            task.cancel()
        revocations.unregister(user.session_id, revoked)


@router.websocket("/ws/cameras/{camera_id}/frames")
async def camera_frames_stream(
    ws: WebSocket,
    camera_id: str,
    user: CurrentUser = Depends(require_ws_permission(Permission.CAMERA_READ)),
) -> None:
    if not await _camera_exists(camera_id):
        await ws.close(code=1008, reason="unknown camera")
        return
    viewers = _get_frame_viewers(ws)
    if not viewers.acquire():
        await ws.close(code=1008, reason="viewer limit reached")
        logger.warning("frame viewer rejected camera=%s cap reached", camera_id)
        return
    try:
        await _stream_frames(ws, camera_id, user)
    finally:
        viewers.release()
