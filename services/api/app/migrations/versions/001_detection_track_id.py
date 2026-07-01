from __future__ import annotations

import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

VERSION = 1
NAME = "detection_track_id"

_COLLECTION = "detections"
_FIELDS = {"track_id": 0, "detection_present": False}


async def up(db: AsyncIOMotorDatabase) -> None:
    collection = db[_COLLECTION]
    filter_query = {"track_id": {"$exists": False}}
    update = {"$set": _FIELDS}
    result = await collection.update_many(filter_query, update)
    logger.info(
        "migration 001 up: matched=%s modified=%s collection=%s",
        result.matched_count,
        result.modified_count,
        _COLLECTION,
    )


async def down(db: AsyncIOMotorDatabase) -> None:
    collection = db[_COLLECTION]
    filter_query = {"track_id": {"$exists": True}}
    update = {"$unset": {field: "" for field in _FIELDS}}
    result = await collection.update_many(filter_query, update)
    logger.info(
        "migration 001 down: matched=%s modified=%s collection=%s",
        result.matched_count,
        result.modified_count,
        _COLLECTION,
    )
