from __future__ import annotations

import logging

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import OperationFailure

logger = logging.getLogger(__name__)

VERSION = 5
NAME = "alert_decision_keys"

_ALERTS = "alerts"
_UNSPECIFIED = "DECISION_UNSPECIFIED"

_DECIDED_INDEX = "decided_at_-1__id_-1_partial"
_DECISION_INDEX = "decision_1_decided_at_-1__id_-1_partial"
_DECIDED_ONLY = {"decided_at": {"$type": "date"}}


async def _backfill_decision(db: AsyncIOMotorDatabase) -> None:
    result = await db[_ALERTS].update_many(
        {"decision": {"$exists": False}},
        {"$set": {"decision": _UNSPECIFIED}},
    )
    logger.info(
        "migration 005 up: alerts.decision defaulted matched=%s modified=%s",
        result.matched_count,
        result.modified_count,
    )
    orphans = await db[_ALERTS].count_documents({"decision": {"$exists": False}})
    if orphans:
        logger.warning(
            "migration 005 up: %s alerts still without decision, history filter will skip them",
            orphans,
        )


async def _drop_index(db: AsyncIOMotorDatabase, name: str) -> None:
    try:
        await db[_ALERTS].drop_index(name)
        logger.info("migration 005: dropped index %s", name)
    except OperationFailure as exc:
        logger.info("migration 005: index %s not dropped: %s", name, exc)


async def up(db: AsyncIOMotorDatabase) -> None:
    await _backfill_decision(db)

    await db[_ALERTS].create_index(
        [("decided_at", -1), ("_id", -1)],
        name=_DECIDED_INDEX,
        partialFilterExpression=_DECIDED_ONLY,
    )
    await db[_ALERTS].create_index(
        [("decision", 1), ("decided_at", -1), ("_id", -1)],
        name=_DECISION_INDEX,
        partialFilterExpression=_DECIDED_ONLY,
    )
    logger.info("migration 005 up: indexes %s, %s created", _DECIDED_INDEX, _DECISION_INDEX)


async def down(db: AsyncIOMotorDatabase) -> None:
    await _drop_index(db, _DECIDED_INDEX)
    await _drop_index(db, _DECISION_INDEX)
    result = await db[_ALERTS].update_many(
        {"decision": _UNSPECIFIED, "decided_at": {"$exists": False}},
        {"$unset": {"decision": ""}},
    )
    logger.info(
        "migration 005 down: alerts.decision removed matched=%s modified=%s",
        result.matched_count,
        result.modified_count,
    )
