from __future__ import annotations

import logging

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError, OperationFailure

logger = logging.getLogger(__name__)

VERSION = 8
NAME = "detection_policy_keys"

_POLICY = "detection_policy"
_VERSION_INDEX = "version_1"
_CHANGED_INDEX = "changed_at_-1"


async def _assert_unique(db: AsyncIOMotorDatabase) -> None:
    pipeline = [
        {"$group": {"_id": "$version", "count": {"$sum": 1}}},
        {"$match": {"count": {"$gt": 1}}},
        {"$limit": 5},
    ]
    clashes = [doc async for doc in db[_POLICY].aggregate(pipeline)]
    if not clashes:
        return
    values = ", ".join(repr(doc["_id"]) for doc in clashes)
    raise DuplicateKeyError(
        f"migration 008 up: {_POLICY}.version holds duplicates, resolve before applying: {values}"
    )


async def _drop_index(db: AsyncIOMotorDatabase, name: str) -> None:
    try:
        await db[_POLICY].drop_index(name)
        logger.info("migration 008: dropped index %s", name)
    except OperationFailure as exc:
        logger.info("migration 008: index %s not dropped: %s", name, exc)


async def up(db: AsyncIOMotorDatabase) -> None:
    await _assert_unique(db)
    await db[_POLICY].create_index("version", name=_VERSION_INDEX, unique=True)
    await db[_POLICY].create_index([("changed_at", -1)], name=_CHANGED_INDEX)
    logger.info("migration 008 up: adopted %s, %s", _VERSION_INDEX, _CHANGED_INDEX)


async def down(db: AsyncIOMotorDatabase) -> None:
    await _drop_index(db, _VERSION_INDEX)
    await _drop_index(db, _CHANGED_INDEX)
