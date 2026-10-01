import asyncio
import json

from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings
from app.core.database import _resolve_mongodb_url
from app.core.redis import close_redis, open_stream_redis
from app.repositories.policy_repository import PolicyRepository
from app.services.policy_sync import POLICY_CURRENT_KEY


async def main() -> None:
    client = AsyncIOMotorClient(_resolve_mongodb_url())
    doc = await PolicyRepository(client[settings.DATABASE_NAME].detection_policy).current()
    stream = await open_stream_redis()
    raw = await stream.get(POLICY_CURRENT_KEY)
    mongo = doc["version"] if doc else None
    held = json.loads(raw)["version"] if raw else None
    print(f"policy mongo={mongo} redis={held} {'match' if mongo == held else 'MISMATCH'}")
    await close_redis(stream)
    client.close()


asyncio.run(main())
