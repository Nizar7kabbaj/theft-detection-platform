from __future__ import annotations

import logging

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import OperationFailure

logger = logging.getLogger(__name__)

VERSION = 3
NAME = "alert_pagination_keys"

_ALERTS = "alerts"
_LEGACY_INDEX = "acknowledged_1_created_at_-1"
_SEVERITY_INDEX = "severity_1_created_at_-1__id_-1"
_RECENT_INDEX = "created_at_-1__id_-1"


async def _backfill_created_at(db: AsyncIOMotorDatabase) -> None:
    result = await db[_ALERTS].update_many(
        {"created_at": {"$exists": False}, "occurred_at": {"$exists": True}},
        [{"$set": {"created_at": "$occurred_at"}}],
    )
    logger.info(
        "migration 003 up: alerts.created_at backfilled matched=%s modified=%s",
        result.matched_count,
        result.modified_count,
    )
    orphans = await db[_ALERTS].count_documents({"created_at": {"$exists": False}})
    if orphans:
        logger.warning(
            "migration 003 up: %s alerts still without created_at, sort order undefined for them",
            orphans,
        )


async def _backfill_acknowledged(db: AsyncIOMotorDatabase) -> None:
    result = await db[_ALERTS].update_many(
        {"acknowledged": {"$exists": False}},
        {"$set": {"acknowledged": False}},
    )
    logger.info(
        "migration 003 up: alerts.acknowledged defaulted matched=%s modified=%s",
        result.matched_count,
        result.modified_count,
    )


async def _drop_index(db: AsyncIOMotorDatabase, name: str) -> None:
    try:
        await db[_ALERTS].drop_index(name)
        logger.info("migration 003: dropped index %s", name)
    except OperationFailure as exc:
        logger.info("migration 003: index %s not dropped: %s", name, exc)


async def up(db: AsyncIOMotorDatabase) -> None:
    await _backfill_created_at(db)
    await _backfill_acknowledged(db)
    await _drop_index(db, _LEGACY_INDEX)
    await db[_ALERTS].create_index(
        [("created_at", -1), ("_id", -1)],
        name=_RECENT_INDEX,
    )
    await db[_ALERTS].create_index(
        [("severity", 1), ("created_at", -1), ("_id", -1)],
        name=_SEVERITY_INDEX,
    )
    logger.info("migration 003 up: indexes %s, %s created", _RECENT_INDEX, _SEVERITY_INDEX)


async def down(db: AsyncIOMotorDatabase) -> None:
    await _drop_index(db, _RECENT_INDEX)
    await _drop_index(db, _SEVERITY_INDEX)
    await db[_ALERTS].create_index(
        [("acknowledged", 1), ("created_at", -1)],
        name=_LEGACY_INDEX,
    )
    result = await db[_ALERTS].update_many(
        {"created_at": {"$exists": True}},
        {"$unset": {"created_at": ""}},
    )
    logger.info(
        "migration 003 down: alerts.created_at removed matched=%s modified=%s",
        result.matched_count,
        result.modified_count,
    )
