from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

VERSION = 2
NAME = "alert_document_shape"

_DETECTIONS = "detections"
_ALERTS = "alerts"

_INFERENCE_STATE_MAP = {
    "warming_up": "INFERENCE_STATE_WARMING_UP",
    "normal": "INFERENCE_STATE_NORMAL",
    "anomaly": "INFERENCE_STATE_ANOMALY",
}

_SEVERITY_MAP = {
    "HIGH": "SEVERITY_WARNING",
    "MEDIUM": "SEVERITY_NOTICE",
    "LOW": "SEVERITY_INFO",
    "CRITICAL": "SEVERITY_CRITICAL",
}

_ALERT_TYPE_MAP = {
    "object_proximity": "ALERT_TYPE_OBJECT_PROXIMITY",
    "bending": "ALERT_TYPE_BENDING",
    "loitering": "ALERT_TYPE_LOITERING",
}

_SEVERITY_REVERSE = {v: k for k, v in _SEVERITY_MAP.items()}
_ALERT_TYPE_REVERSE = {v: k for k, v in _ALERT_TYPE_MAP.items()}
_INFERENCE_STATE_REVERSE = {v: k for k, v in _INFERENCE_STATE_MAP.items()}


async def _rewrite_field(
    db: AsyncIOMotorDatabase,
    collection_name: str,
    field: str,
    mapping: dict[str, str],
    label: str,
) -> None:
    collection = db[collection_name]
    for old_value, new_value in mapping.items():
        result = await collection.update_many(
            {field: old_value},
            {"$set": {field: new_value}},
        )
        if result.matched_count:
            logger.info(
                "migration 002 %s: %s.%s %s -> %s matched=%s modified=%s",
                label,
                collection_name,
                field,
                old_value,
                new_value,
                result.matched_count,
                result.modified_count,
            )


async def _rewrite_field_ci(
    db: AsyncIOMotorDatabase,
    collection_name: str,
    field: str,
    mapping: dict[str, str],
    label: str,
) -> None:
    collection = db[collection_name]
    for old_value, new_value in mapping.items():
        pattern = f"^{re.escape(old_value)}$"
        result = await collection.update_many(
            {field: {"$regex": pattern, "$options": "i"}},
            {"$set": {field: new_value}},
        )
        if result.matched_count:
            logger.info(
                "migration 002 %s: %s.%s %s -> %s matched=%s modified=%s",
                label,
                collection_name,
                field,
                old_value,
                new_value,
                result.matched_count,
                result.modified_count,
            )


async def _rename_timestamp_to_occurred_at(
    db: AsyncIOMotorDatabase, collection_name: str
) -> None:
    collection = db[collection_name]
    cursor = collection.find(
        {"timestamp": {"$type": "string"}, "occurred_at": {"$exists": False}}
    )
    converted = 0
    skipped = 0
    async for doc in cursor:
        raw = doc.get("timestamp")
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            logger.warning(
                "migration 002 up: unparseable timestamp doc=%s value=%r",
                doc["_id"],
                raw,
            )
            skipped += 1
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        await collection.update_one(
            {"_id": doc["_id"]},
            {"$set": {"occurred_at": parsed}, "$unset": {"timestamp": ""}},
        )
        converted += 1
    logger.info(
        "migration 002 up: %s timestamp -> occurred_at converted=%s skipped=%s",
        collection_name,
        converted,
        skipped,
    )


async def _drop_torso_angle(db: AsyncIOMotorDatabase) -> None:
    result = await db[_ALERTS].update_many(
        {"torso_angle": {"$exists": True}},
        {"$unset": {"torso_angle": ""}},
    )
    if result.matched_count:
        logger.info(
            "migration 002 up: alerts.torso_angle dropped matched=%s modified=%s",
            result.matched_count,
            result.modified_count,
        )


async def _rename_occurred_at_to_timestamp(
    db: AsyncIOMotorDatabase, collection_name: str
) -> None:
    collection = db[collection_name]
    cursor = collection.find({"occurred_at": {"$type": "date"}})
    reverted = 0
    async for doc in cursor:
        occurred_at = doc["occurred_at"]
        iso = occurred_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        await collection.update_one(
            {"_id": doc["_id"]},
            {"$set": {"timestamp": iso}, "$unset": {"occurred_at": ""}},
        )
        reverted += 1
    logger.info(
        "migration 002 down: %s occurred_at -> timestamp reverted=%s",
        collection_name,
        reverted,
    )


async def up(db: AsyncIOMotorDatabase) -> None:
    await _rewrite_field(db, _DETECTIONS, "class_name", _INFERENCE_STATE_MAP, "up")
    await _rewrite_field_ci(db, _ALERTS, "severity", _SEVERITY_MAP, "up")
    await _rewrite_field(db, _ALERTS, "alert_type", _ALERT_TYPE_MAP, "up")
    await _rename_timestamp_to_occurred_at(db, _DETECTIONS)
    await _rename_timestamp_to_occurred_at(db, _ALERTS)
    await _drop_torso_angle(db)


async def down(db: AsyncIOMotorDatabase) -> None:
    await _rewrite_field(db, _DETECTIONS, "class_name", _INFERENCE_STATE_REVERSE, "down")
    await _rewrite_field(db, _ALERTS, "severity", _SEVERITY_REVERSE, "down")
    await _rewrite_field(db, _ALERTS, "alert_type", _ALERT_TYPE_REVERSE, "down")
    await _rename_occurred_at_to_timestamp(db, _DETECTIONS)
    await _rename_occurred_at_to_timestamp(db, _ALERTS)
