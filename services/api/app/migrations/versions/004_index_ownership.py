from __future__ import annotations

import logging

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError, OperationFailure

logger = logging.getLogger(__name__)

VERSION = 4
NAME = "index_ownership"

_ALERTS = "alerts"
_CAMERAS = "cameras"
_DETECTIONS = "detections"

_LEGACY_ALERT_INDEX = "acknowledged_1_created_at_-1"
_CAMERA_NAME_INDEX = "name_1"
_CAMERA_ID_INDEX = "camera_id_1"
_DETECTION_SESSION_INDEX = "session_id_1_occurred_at_-1"


async def _assert_unique(db: AsyncIOMotorDatabase, collection: str, field: str) -> None:
    pipeline = [
        {"$group": {"_id": f"${field}", "count": {"$sum": 1}}},
        {"$match": {"count": {"$gt": 1}}},
        {"$limit": 5},
    ]
    clashes = [doc async for doc in db[collection].aggregate(pipeline)]
    if not clashes:
        return
    values = ", ".join(repr(doc["_id"]) for doc in clashes)
    raise DuplicateKeyError(
        f"migration 004 up: {collection}.{field} holds duplicates, resolve before applying: {values}"
    )


async def _drop_index(db: AsyncIOMotorDatabase, collection: str, name: str) -> None:
    try:
        await db[collection].drop_index(name)
        logger.info("migration 004: dropped index %s.%s", collection, name)
    except OperationFailure as exc:
        logger.info("migration 004: index %s.%s not dropped: %s", collection, name, exc)


async def up(db: AsyncIOMotorDatabase) -> None:
    await _assert_unique(db, _CAMERAS, "name")
    await _assert_unique(db, _CAMERAS, "camera_id")

    await db[_CAMERAS].create_index("name", name=_CAMERA_NAME_INDEX, unique=True)
    await db[_CAMERAS].create_index("camera_id", name=_CAMERA_ID_INDEX, unique=True)
    await db[_DETECTIONS].create_index(
        [("session_id", 1), ("occurred_at", -1)],
        name=_DETECTION_SESSION_INDEX,
    )
    logger.info(
        "migration 004 up: adopted %s, %s, %s",
        _CAMERA_NAME_INDEX,
        _CAMERA_ID_INDEX,
        _DETECTION_SESSION_INDEX,
    )

    await _drop_index(db, _ALERTS, _LEGACY_ALERT_INDEX)


async def down(db: AsyncIOMotorDatabase) -> None:
    await db[_ALERTS].create_index(
        [("acknowledged", 1), ("created_at", -1)],
        name=_LEGACY_ALERT_INDEX,
    )
    logger.info("migration 004 down: restored %s", _LEGACY_ALERT_INDEX)
