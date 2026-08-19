from __future__ import annotations

import asyncio
import contextlib
import json
import logging

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import PyMongoError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.services.camera_health import HealthState, read_health

logger = logging.getLogger(__name__)

_CHANNEL = "cameras:health"


async def _camera_ids(db: AsyncIOMotorDatabase) -> list[str]:
    ids: list[str] = []
    cursor = db.cameras.find({}, {"camera_id": 1})
    async for doc in cursor:
        ids.append(str(doc["camera_id"]))
    return ids


async def _publish_transition(
    publisher: Redis,
    camera_id: str,
    state: HealthState,
    last_frame_at: float | None,
    age_seconds: float | None,
) -> None:
    payload = json.dumps(
        {
            "camera_id": camera_id,
            "state": state.value,
            "last_frame_at": last_frame_at,
            "age_seconds": age_seconds,
        }
    )
    try:
        await publisher.publish(_CHANNEL, payload)
    except RedisError as exc:
        logger.warning("health publish failed camera=%s: %s", camera_id, exc)


async def run_reconcile(
    db: AsyncIOMotorDatabase,
    stream: Redis,
    publisher: Redis,
    stop: asyncio.Event,
) -> None:
    last_state: dict[str, HealthState] = {}
    interval = settings.HEALTH_RECONCILE_INTERVAL_SECONDS
    logger.info("health reconcile started interval=%.1fs", interval)

    while not stop.is_set():
        try:
            camera_ids = await _camera_ids(db)
            seen: set[str] = set()
            for camera_id in camera_ids:
                seen.add(camera_id)
                health = await read_health(stream, camera_id)
                if last_state.get(camera_id) != health.state:
                    last_state[camera_id] = health.state
                    await _publish_transition(
                        publisher,
                        camera_id,
                        health.state,
                        health.last_frame_at,
                        health.age_seconds,
                    )
            for gone in set(last_state) - seen:
                del last_state[gone]
        except PyMongoError as exc:
            logger.error("reconcile tick failed: %s", exc)

        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=interval)

    logger.info("health reconcile stopped")
