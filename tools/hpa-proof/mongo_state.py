import asyncio

from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings
from app.core.database import _resolve_mongodb_url


async def main() -> None:
    client = AsyncIOMotorClient(_resolve_mongodb_url())
    db = client[settings.DATABASE_NAME]
    applied = sorted([doc["version"] async for doc in db["_migrations"].find({}, {"version": 1})])
    print("applied migrations", applied)
    for name in ("alerts", "cameras", "detection_policy", "audit_outbox"):
        indexes = await db[name].index_information()
        unique = {key: spec.get("unique", False) for key, spec in indexes.items()}
        print(name, unique)
    client.close()


asyncio.run(main())
