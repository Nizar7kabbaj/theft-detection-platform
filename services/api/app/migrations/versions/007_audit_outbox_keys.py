from __future__ import annotations

import logging

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError, OperationFailure

logger = logging.getLogger(__name__)

VERSION = 7
NAME = "audit_outbox_keys"

_OUTBOX = "audit_outbox"
_ATTEMPT_INDEX = "next_attempt_at_1"
_EVENT_INDEX = "event_id_1"


async def _assert_unique(db: AsyncIOMotorDatabase) -> None:
    pipeline = [
        {"$group": {"_id": "$event_id", "count": {"$sum": 1}}},
        {"$match": {"count": {"$gt": 1}}},
        {"$limit": 5},
    ]
    clashes = [doc async for doc in db[_OUTBOX].aggregate(pipeline)]
    if not clashes:
        return
    values = ", ".join(repr(doc["_id"]) for doc in clashes)
    raise DuplicateKeyError(
        f"migration 007 up: {_OUTBOX}.event_id holds duplicates, resolve before applying: {values}"
    )


async def _drop_index(db: AsyncIOMotorDatabase, name: str) -> None:
    try:
        await db[_OUTBOX].drop_index(name)
        logger.info("migration 007: dropped index %s", name)
    except OperationFailure as exc:
        logger.info("migration 007: index %s not dropped: %s", name, exc)


async def up(db: AsyncIOMotorDatabase) -> None:
    await _assert_unique(db)
    await db[_OUTBOX].create_index("next_attempt_at", name=_ATTEMPT_INDEX)
    await db[_OUTBOX].create_index("event_id", name=_EVENT_INDEX, unique=True)
    logger.info("migration 007 up: adopted %s, %s", _ATTEMPT_INDEX, _EVENT_INDEX)


async def down(db: AsyncIOMotorDatabase) -> None:
    await _drop_index(db, _ATTEMPT_INDEX)
    await _drop_index(db, _EVENT_INDEX)
