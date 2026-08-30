from __future__ import annotations

import asyncio
import json
import logging
import time

from fastapi import WebSocket
from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.websockets import WebSocketState

from app.core.config import settings
from app.services.camera_health import HealthState

logger = logging.getLogger(__name__)

_PAYLOAD_FIELD = b"payload"
_BODY_FIELD = b"body"


class ViewerLimit:
    def __init__(self, maximum: int) -> None:
        self._maximum = maximum
        self._active = 0

    @property
    def active(self) -> int:
        return self._active

    def acquire(self) -> bool:
        if self._active >= self._maximum:
            return False
        self._active += 1
        return True

    def release(self) -> None:
        if self._active > 0:
            self._active -= 1


def _entry_age(entry_id: bytes, now: float) -> float | None:
    ms_part, _, _ = entry_id.decode("ascii", "ignore").partition("-")
    try:
        entry_ms = int(ms_part)
    except ValueError:
        return None
    age = now - (entry_ms / 1000.0)
    return age if age >= 0 else 0.0


def _state_for(age: float | None) -> HealthState:
    if age is None:
        return HealthState.UNKNOWN
    if age <= settings.HEALTH_ONLINE_MAX_AGE_SECONDS:
        return HealthState.ONLINE
    if age <= settings.HEALTH_DEGRADED_MAX_AGE_SECONDS:
        return HealthState.DEGRADED
    return HealthState.OFFLINE


async def _send_state(ws: WebSocket, state: HealthState, age: float | None) -> None:
    await ws.send_text(
        json.dumps({"event": "state", "data": {"state": state.value, "age_seconds": age}})
    )


async def _send_detection(ws: WebSocket, body: bytes) -> None:
    try:
        data = json.loads(body)
    except ValueError:
        return
    await ws.send_text(json.dumps({"event": "detection", "data": data}))


async def _read_detection(
    stream: Redis, camera_id: str, last_entry: bytes
) -> tuple[bytes, bytes | None]:
    key = f"{settings.STREAM_DETECT_PREFIX}:{camera_id}"
    try:
        entries = await stream.xrevrange(key, count=1)
    except RedisError:
        return last_entry, None
    if not entries:
        return last_entry, None
    entry_id, fields = entries[0]
    if entry_id == last_entry:
        return last_entry, None
    body = fields.get(_BODY_FIELD)
    return entry_id, body


async def run_frame_pump(ws: WebSocket, stream: Redis, camera_id: str) -> None:
    key = f"{settings.STREAM_FRAME_PREFIX}:{camera_id}"
    interval = settings.FRAME_STREAM_INTERVAL_SECONDS
    send_timeout = settings.FRAME_STREAM_SEND_TIMEOUT_SECONDS
    max_failures = settings.FRAME_STREAM_MAX_READ_FAILURES
    failures = 0
    last_entry = b""
    last_detect_entry = b""
    last_state: HealthState | None = None
    while ws.client_state == WebSocketState.CONNECTED:
        try:
            entries = await stream.xrevrange(key, count=1)
        except RedisError as exc:
            failures += 1
            logger.warning("frame read failed camera=%s: %s", camera_id, exc)
            if failures >= max_failures and last_state is not HealthState.UNKNOWN:
                await _send_state(ws, HealthState.UNKNOWN, None)
                last_state = HealthState.UNKNOWN
            await asyncio.sleep(interval)
            continue
        failures = 0
        now = time.time()
        if not entries:
            if last_state is not HealthState.OFFLINE:
                await _send_state(ws, HealthState.OFFLINE, None)
                last_state = HealthState.OFFLINE
            await asyncio.sleep(interval)
            continue
        entry_id, fields = entries[0]
        age = _entry_age(entry_id, now)
        state = _state_for(age)
        if state is not last_state:
            await _send_state(ws, state, age)
            last_state = state
        payload = fields.get(_PAYLOAD_FIELD)
        if payload is None or entry_id == last_entry or state is HealthState.OFFLINE:
            await asyncio.sleep(interval)
            continue
        last_entry = entry_id
        try:
            await asyncio.wait_for(ws.send_bytes(payload), send_timeout)
        except TimeoutError:
            logger.info("frame send timed out camera=%s, dropping viewer", camera_id)
            return
        last_detect_entry, body = await _read_detection(stream, camera_id, last_detect_entry)
        if body is not None:
            await _send_detection(ws, body)
        await asyncio.sleep(interval)
