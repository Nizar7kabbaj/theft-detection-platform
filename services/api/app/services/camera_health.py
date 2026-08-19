from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import StrEnum

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)


class HealthState(StrEnum):
    ONLINE = "online"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class CameraHealth:
    state: HealthState
    last_frame_at: float | None
    age_seconds: float | None


def _derive_state(age_seconds: float | None) -> HealthState:
    if age_seconds is None:
        return HealthState.OFFLINE
    if age_seconds <= settings.HEALTH_ONLINE_MAX_AGE_SECONDS:
        return HealthState.ONLINE
    if age_seconds <= settings.HEALTH_DEGRADED_MAX_AGE_SECONDS:
        return HealthState.DEGRADED
    return HealthState.OFFLINE


def _frame_age(entry_id: str | bytes, now: float) -> float | None:
    raw = entry_id.decode("ascii", "ignore") if isinstance(entry_id, bytes) else entry_id
    ms_part, _, _ = raw.partition("-")
    try:
        entry_ms = int(ms_part)
    except ValueError:
        return None
    age = now - (entry_ms / 1000.0)
    return age if age >= 0 else 0.0


async def read_health(stream: Redis, camera_id: str) -> CameraHealth:
    key = f"{settings.STREAM_FRAME_PREFIX}:{camera_id}"
    try:
        entries = await stream.xrevrange(key, count=1)
    except RedisError as exc:
        logger.warning("stream read failed camera=%s: %s", camera_id, exc)
        return CameraHealth(HealthState.UNKNOWN, None, None)

    if not entries:
        return CameraHealth(HealthState.OFFLINE, None, None)

    now = time.time()
    entry_id, _fields = entries[0]
    age = _frame_age(entry_id, now)
    if age is None:
        return CameraHealth(HealthState.UNKNOWN, None, None)

    last_frame_at = now - age
    return CameraHealth(_derive_state(age), last_frame_at, age)
