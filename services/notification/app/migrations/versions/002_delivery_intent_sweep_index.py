from __future__ import annotations
import logging
from pymongo import ASCENDING
from motor.motor_asyncio import AsyncIOMotorDatabase
logger = logging.getLogger(__name__)
VERSION = 2
NAME = "delivery_intent_sweep_index"
_COLLECTION = "delivery_intents"
_INDEX_NAME = "delivery_status_updated_at"
_KEYS = [
    ("status", ASCENDING),
    ("updated_at", ASCENDING),
]
async def up(db: AsyncIOMotorDatabase) -> None:
    name = await db[_COLLECTION].create_index(_KEYS, name=_INDEX_NAME)
    logger.info("migration 002 up: ensured index %s on %s", name, _COLLECTION)
async def down(db: AsyncIOMotorDatabase) -> None:
    existing = await db[_COLLECTION].index_information()
    if _INDEX_NAME not in existing:
        logger.info("migration 002 down: index %s absent on %s", _INDEX_NAME, _COLLECTION)
        return
    await db[_COLLECTION].drop_index(_INDEX_NAME)
    logger.info("migration 002 down: dropped index %s on %s", _INDEX_NAME, _COLLECTION)
