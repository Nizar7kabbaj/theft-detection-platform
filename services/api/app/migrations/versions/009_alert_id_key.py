from __future__ import annotations

import logging

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError, OperationFailure

logger = logging.getLogger(__name__)

VERSION = 9
NAME = "alert_id_key"

_ALERTS = "alerts"
_ALERT_ID_INDEX = "alert_id_1"
_HAS_ALERT_ID = {"alert_id": {"$type": "string"}}


async def _assert_unique(db: AsyncIOMotorDatabase) -> None:
    pipeline = [
        {"$match": _HAS_ALERT_ID},
        {"$group": {"_id": "$alert_id", "count": {"$sum": 1}}},
        {"$match": {"count": {"$gt": 1}}},
        {"$limit": 5},
    ]
    clashes = [doc async for doc in db[_ALERTS].aggregate(pipeline)]
    if not clashes:
        return
    values = ", ".join(repr(doc["_id"]) for doc in clashes)
    raise DuplicateKeyError(
        f"migration 009 up: {_ALERTS}.alert_id holds duplicates, resolve before applying: {values}"
    )


async def up(db: AsyncIOMotorDatabase) -> None:
    await _assert_unique(db)
    await db[_ALERTS].create_index(
        "alert_id",
        name=_ALERT_ID_INDEX,
        unique=True,
        partialFilterExpression=_HAS_ALERT_ID,
    )
    logger.info("migration 009 up: adopted %s", _ALERT_ID_INDEX)


async def down(db: AsyncIOMotorDatabase) -> None:
    try:
        await db[_ALERTS].drop_index(_ALERT_ID_INDEX)
        logger.info("migration 009: dropped index %s", _ALERT_ID_INDEX)
    except OperationFailure as exc:
        logger.info("migration 009: index %s not dropped: %s", _ALERT_ID_INDEX, exc)
