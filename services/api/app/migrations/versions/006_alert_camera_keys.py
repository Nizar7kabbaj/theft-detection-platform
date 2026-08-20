from __future__ import annotations

import logging

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import OperationFailure

logger = logging.getLogger(__name__)

VERSION = 6
NAME = "alert_camera_keys"

_ALERTS = "alerts"
_CAMERA_RECENT_INDEX = "camera_id_1_created_at_-1__id_-1"
_CAMERA_DECIDED_INDEX = "camera_id_1_decided_at_-1__id_-1_partial"
_DECIDED_ONLY = {"decided_at": {"$type": "date"}}


async def _report_missing_camera(db: AsyncIOMotorDatabase) -> None:
    orphans = await db[_ALERTS].count_documents({"camera_id": {"$exists": False}})
    if orphans:
        logger.warning(
            "migration 006 up: %s alerts without camera_id, they index as null",
            orphans,
        )


async def _drop_index(db: AsyncIOMotorDatabase, name: str) -> None:
    try:
        await db[_ALERTS].drop_index(name)
        logger.info("migration 006: dropped index %s", name)
    except OperationFailure as exc:
        logger.info("migration 006: index %s not dropped: %s", name, exc)


async def up(db: AsyncIOMotorDatabase) -> None:
    await _report_missing_camera(db)
    await db[_ALERTS].create_index(
        [("camera_id", 1), ("created_at", -1), ("_id", -1)],
        name=_CAMERA_RECENT_INDEX,
    )
    await db[_ALERTS].create_index(
        [("camera_id", 1), ("decided_at", -1), ("_id", -1)],
        name=_CAMERA_DECIDED_INDEX,
        partialFilterExpression=_DECIDED_ONLY,
    )
    logger.info(
        "migration 006 up: indexes %s, %s created",
        _CAMERA_RECENT_INDEX,
        _CAMERA_DECIDED_INDEX,
    )


async def down(db: AsyncIOMotorDatabase) -> None:
    await _drop_index(db, _CAMERA_RECENT_INDEX)
    await _drop_index(db, _CAMERA_DECIDED_INDEX)
