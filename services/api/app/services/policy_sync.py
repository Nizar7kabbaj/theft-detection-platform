from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import PyMongoError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.repositories.policy_repository import PolicyRepository
from app.schemas.policy import PolicyPayload, PolicyResponse

logger = logging.getLogger(__name__)

POLICY_CURRENT_KEY = "policy:detection:current"
POLICY_CHANNEL = "policy:detection"


def policy_message(version: int, policy: PolicyPayload) -> str:
    return PolicyResponse(
        version=version,
        policy=policy,
        changed_by="",
        changed_at=datetime.now(UTC),
    ).model_dump_json(exclude={"runtime", "changed_by", "changed_at"})


async def _stored_version(stream: Redis) -> int:
    raw = await stream.get(POLICY_CURRENT_KEY)
    if raw is None:
        return 0
    return int(json.loads(raw)["version"])


async def _sync_once(repo: PolicyRepository, stream: Redis) -> None:
    doc = await repo.current()
    if doc is None:
        return
    version = int(doc["version"])
    if await _stored_version(stream) >= version:
        return
    body = policy_message(version, PolicyPayload.model_validate(doc["policy"]))
    await stream.set(POLICY_CURRENT_KEY, body)
    await stream.publish(POLICY_CHANNEL, body)
    logger.info("detection policy restored to stream version=%d", version)


async def run_policy_sync(
    db: AsyncIOMotorDatabase,
    stream: Redis,
    stop: asyncio.Event,
) -> None:
    repo = PolicyRepository(db.detection_policy)
    interval = settings.POLICY_SYNC_INTERVAL_SECONDS
    logger.info("policy sync started interval=%.1fs", interval)
    while not stop.is_set():
        try:
            await _sync_once(repo, stream)
        except (RedisError, PyMongoError, ValueError, KeyError) as exc:
            logger.warning("policy sync tick failed: %s", exc)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=interval)
    logger.info("policy sync stopped")
