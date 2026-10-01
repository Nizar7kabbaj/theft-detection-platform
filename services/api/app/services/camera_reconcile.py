from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import math
import time

from motor.motor_asyncio import AsyncIOMotorDatabase
from redis.asyncio import Redis
from redis.commands.core import AsyncScript
from redis.exceptions import RedisError

from app.core.config import settings
from app.services.camera_health import CameraHealth, read_health_many

logger = logging.getLogger(__name__)

_CHANNEL = "cameras:health"
_STATE_KEY_PREFIX = "health:camera:"
_STATE_TTL_INTERVALS = 10
TRANSITION_LUA = """
local observed = tonumber(ARGV[2])
local current = redis.call('get', KEYS[1])
local previous = nil
if current then
    local sep = string.find(current, '|', 1, true)
    if sep then
        local seen = tonumber(string.sub(current, sep + 1))
        if seen and observed <= seen then
            return 0
        end
        previous = string.sub(current, 1, sep - 1)
    end
end
redis.call('set', KEYS[1], ARGV[1] .. '|' .. ARGV[2], 'EX', ARGV[3])
if previous == ARGV[1] then
    return 0
end
redis.call('publish', ARGV[4], ARGV[5])
return 1
"""


def state_key(camera_id: str) -> str:
    return f"{_STATE_KEY_PREFIX}{camera_id}"


async def _camera_ids(db: AsyncIOMotorDatabase) -> list[str]:
    ids: list[str] = []
    cursor = db.cameras.find({}, {"camera_id": 1})
    async for doc in cursor:
        ids.append(str(doc["camera_id"]))
    return ids


async def _publish_if_changed(
    script: AsyncScript,
    camera_id: str,
    health: CameraHealth,
    observed_ms: int,
    ttl_seconds: int,
) -> bool:
    payload = json.dumps(
        {
            "camera_id": camera_id,
            "state": health.state.value,
            "last_frame_at": health.last_frame_at,
            "age_seconds": health.age_seconds,
        }
    )
    try:
        published = await script(
            keys=[state_key(camera_id)],
            args=[health.state.value, observed_ms, ttl_seconds, _CHANNEL, payload],
        )
    except RedisError as exc:
        logger.warning("health publish failed camera=%s: %s", camera_id, exc)
        return False
    return bool(published)


async def run_reconcile(
    db: AsyncIOMotorDatabase,
    stream: Redis,
    publisher: Redis,
    stop: asyncio.Event,
) -> None:
    interval = settings.HEALTH_RECONCILE_INTERVAL_SECONDS
    ttl_seconds = math.ceil(interval * _STATE_TTL_INTERVALS)
    script = publisher.register_script(TRANSITION_LUA)
    logger.info("health reconcile started interval=%.1fs", interval)

    while not stop.is_set():
        try:
            camera_ids = await _camera_ids(db)
            observed_ms = time.time_ns() // 1_000_000
            healths = await read_health_many(stream, camera_ids)
            for camera_id, health in healths.items():
                await _publish_if_changed(script, camera_id, health, observed_ms, ttl_seconds)
        except Exception:
            logger.exception("reconcile tick failed")

        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=interval)

    logger.info("health reconcile stopped")
