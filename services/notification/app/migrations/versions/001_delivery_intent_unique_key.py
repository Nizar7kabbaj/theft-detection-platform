from __future__ import annotations
import logging
from pymongo import ASCENDING
from motor.motor_asyncio import AsyncIOMotorDatabase
logger = logging.getLogger(__name__)
VERSION = 1
NAME = "delivery_intent_unique_key"
_COLLECTION = "delivery_intents"
_INDEX_NAME = "uniq_delivery_natural_key"
_KEYS = [
    ("source", ASCENDING),
    ("source_ref", ASCENDING),
    ("channel", ASCENDING),
    ("recipient", ASCENDING),
]
async def up(db: AsyncIOMotorDatabase) -> None:
    name = await db[_COLLECTION].create_index(_KEYS, unique=True, name=_INDEX_NAME)
    logger.info("migration 001 up: ensured index %s on %s", name, _COLLECTION)
async def down(db: AsyncIOMotorDatabase) -> None:
    existing = await db[_COLLECTION].index_information()
    if _INDEX_NAME not in existing:
        logger.info("migration 001 down: index %s absent on %s", _INDEX_NAME, _COLLECTION)
        return
    await db[_COLLECTION].drop_index(_INDEX_NAME)
    logger.info("migration 001 down: dropped index %s on %s", _INDEX_NAME, _COLLECTION)
