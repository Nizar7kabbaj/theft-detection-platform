import asyncio
import random
import sys
from datetime import UTC, datetime, timedelta

from motor.motor_asyncio import AsyncIOMotorClient

from app.core.cache import invalidate_prefix
from app.core.config import settings
from app.core.database import _resolve_mongodb_url
from app.core.redis import close_redis, open_redis
from app.repositories.alert_repository import AlertRepository
from app.schemas.alert import AlertCreate, Decision

CAMERAS = [f"cam-load-{n}" for n in range(1, 5)]
SEVERITIES = ["SEVERITY_NOTICE", "SEVERITY_WARNING", "SEVERITY_CRITICAL"]
OBJECTS = ["phone", "bottle", "wallet", "bag"]
WEEK_SECONDS = 7 * 86400
ACTION_ARG = 1
COUNT_ARG = 2
KEYPOINTS = 17


def build(rng: random.Random, index: int, now: datetime) -> dict:
    occurred = now - timedelta(seconds=rng.uniform(0, WEEK_SECONDS))
    payload = AlertCreate.model_validate(
        {
            "alert_id": f"load-{index:06d}",
            "session_id": rng.randint(1, 50),
            "frame_index": rng.randint(0, 50000),
            "occurred_at": occurred,
            "camera_id": rng.choice(CAMERAS),
            "person": {
                "track_id": rng.randint(1, 400),
                "keypoints": [
                    {"x": rng.random(), "y": rng.random(), "confidence": rng.uniform(0.5, 1.0)}
                    for _ in range(KEYPOINTS)
                ],
            },
            "object": {"class_name": rng.choice(OBJECTS)},
            "severity": rng.choice(SEVERITIES),
            "alert_type": "ALERT_TYPE_OBJECT_PROXIMITY",
            "classifier_score": rng.uniform(0.5, 0.99),
        }
    )
    doc = payload.model_dump(mode="json")
    doc["occurred_at"] = payload.occurred_at
    doc["created_at"] = occurred
    doc["acknowledged"] = False
    doc["decision"] = Decision.DECISION_UNSPECIFIED.value
    return doc


async def main() -> None:
    action = sys.argv[ACTION_ARG] if len(sys.argv) > ACTION_ARG else "seed"
    count = int(sys.argv[COUNT_ARG]) if len(sys.argv) > COUNT_ARG else 2000
    client = AsyncIOMotorClient(_resolve_mongodb_url())
    db = client[settings.DATABASE_NAME]
    redis = await open_redis()
    if action == "purge":
        result = await db.alerts.delete_many({"camera_id": {"$in": CAMERAS}})
        print("purged", result.deleted_count, "load alerts")
    else:
        repo = AlertRepository(db.alerts)
        rng = random.SystemRandom()
        now = datetime.now(UTC)
        inserted = 0
        for index in range(count):
            _, fresh = await repo.insert_once(build(rng, index, now))
            inserted += int(fresh)
        print("seeded", inserted, "new alerts,", count - inserted, "already present")
    await invalidate_prefix(redis, "cache:alerts:")
    await close_redis(redis)
    client.close()


asyncio.run(main())
