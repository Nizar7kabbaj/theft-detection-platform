from __future__ import annotations

import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.migrations.runner import _run
from app.shared.config import settings

pytestmark = pytest.mark.integration

INTENT_KEY = [("source", 1), ("source_ref", 1), ("channel", 1), ("recipient", 1)]
SWEEP_KEY = [("status", 1), ("updated_at", 1)]


def _has_index(info: dict, key: list, unique: bool | None = None) -> bool:
    for meta in info.values():
        if list(meta["key"]) == key:
            return unique is None or meta.get("unique", False) == unique
    return False


async def test_up_creates_indexes(raw_db: AsyncIOMotorDatabase) -> None:
    await _run("up", None)
    intents = await raw_db[settings.DELIVERY_INTENT_COLLECTION].index_information()
    dlq = await raw_db[settings.DEAD_LETTER_COLLECTION].index_information()
    assert _has_index(intents, INTENT_KEY, unique=True)
    assert _has_index(intents, SWEEP_KEY)
    assert _has_index(dlq, INTENT_KEY)


async def test_down_drops_indexes(raw_db: AsyncIOMotorDatabase) -> None:
    await _run("up", None)
    await _run("down", None)
    intents = await raw_db[settings.DELIVERY_INTENT_COLLECTION].index_information()
    assert not _has_index(intents, INTENT_KEY, unique=True)
    assert not _has_index(intents, SWEEP_KEY)


async def test_up_is_idempotent(raw_db: AsyncIOMotorDatabase) -> None:
    assert await _run("up", None) == 0
    assert await _run("up", None) == 0
    intents = await raw_db[settings.DELIVERY_INTENT_COLLECTION].index_information()
    assert _has_index(intents, INTENT_KEY, unique=True)
