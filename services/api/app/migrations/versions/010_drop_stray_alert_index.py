from __future__ import annotations

import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

VERSION = 10
NAME = "drop_stray_alert_index"

_ALERTS = "alerts"
_LEGACY_INDEX = "acknowledged_1_created_at_-1"


async def up(db: AsyncIOMotorDatabase) -> None:
    existing = await db[_ALERTS].index_information()
    if _LEGACY_INDEX not in existing:
        logger.info("migration 010 up: %s absent, nothing to drop", _LEGACY_INDEX)
        return
    await db[_ALERTS].drop_index(_LEGACY_INDEX)
    logger.info("migration 010 up: dropped %s", _LEGACY_INDEX)


async def down(db: AsyncIOMotorDatabase) -> None:
    logger.info("migration 010 down: %s stays dropped", _LEGACY_INDEX)
