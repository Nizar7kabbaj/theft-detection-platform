from __future__ import annotations

import asyncio
import contextlib
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
PUBLISH_NEWER_LUA = """
local current = redis.call('get', KEYS[1])
if current then
    local ok, stored = pcall(cjson.decode, current)
    if ok and type(stored) == 'table' then
        local held = tonumber(stored['version'])
        if held and held >= tonumber(ARGV[1]) then
            return 0
        end
    end
end
redis.call('set', KEYS[1], ARGV[2])
redis.call('publish', ARGV[3], ARGV[2])
return 1
"""


def policy_message(version: int, policy: PolicyPayload) -> str:
    return PolicyResponse(
        version=version,
        policy=policy,
        changed_by="",
        changed_at=datetime.now(UTC),
    ).model_dump_json(exclude={"runtime", "changed_by", "changed_at"})


async def publish_policy(stream: Redis, version: int, body: str) -> bool:
    script = stream.register_script(PUBLISH_NEWER_LUA)
    result = await script(keys=[POLICY_CURRENT_KEY], args=[version, body, POLICY_CHANNEL])
    return bool(result)


async def _sync_once(repo: PolicyRepository, stream: Redis) -> None:
    doc = await repo.current()
    if doc is None:
        return
    version = int(doc["version"])
    body = policy_message(version, PolicyPayload.model_validate(doc["policy"]))
    if await publish_policy(stream, version, body):
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
