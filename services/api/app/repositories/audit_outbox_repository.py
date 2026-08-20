from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, ReturnDocument
from pymongo.write_concern import WriteConcern

_COLLECTION = "audit_outbox"
_DEAD_COLLECTION = "audit_outbox_dead"


@dataclass(frozen=True, slots=True)
class PendingEvent:
    id: Any
    event_id: str
    event_bytes: bytes
    occurred_at: datetime
    attempts: int
    created_at: datetime


class AuditOutboxRepository:
    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        durable = WriteConcern(w=1, j=True)
        self._col = database.get_collection(_COLLECTION, write_concern=durable)
        self._dead = database.get_collection(_DEAD_COLLECTION, write_concern=durable)

    async def enqueue(self, event_id: str, event_bytes: bytes, occurred_at: datetime) -> None:
        now = datetime.now(UTC)
        await self._col.insert_one(
            {
                "event_id": event_id,
                "event_bytes": event_bytes,
                "occurred_at": occurred_at,
                "attempts": 0,
                "next_attempt_at": now,
                "created_at": now,
                "claimed_at": None,
            }
        )

    async def claim(self, lease_seconds: float) -> PendingEvent | None:
        now = datetime.now(UTC)
        lease_cutoff = now - timedelta(seconds=lease_seconds)
        document = await self._col.find_one_and_update(
            {
                "next_attempt_at": {"$lte": now},
                "$or": [{"claimed_at": None}, {"claimed_at": {"$lte": lease_cutoff}}],
            },
            {"$set": {"claimed_at": now}},
            sort=[("next_attempt_at", ASCENDING)],
            return_document=ReturnDocument.AFTER,
        )
        if document is None:
            return None
        return PendingEvent(
            id=document["_id"],
            event_id=document["event_id"],
            event_bytes=bytes(document["event_bytes"]),
            occurred_at=document["occurred_at"],
            attempts=document["attempts"],
            created_at=document["created_at"],
        )

    async def release(self, outbox_id: Any) -> None:
        await self._col.delete_one({"_id": outbox_id})

    async def defer(self, outbox_id: Any, next_attempt_at: datetime) -> None:
        await self._col.update_one(
            {"_id": outbox_id},
            {
                "$inc": {"attempts": 1},
                "$set": {"next_attempt_at": next_attempt_at, "claimed_at": None},
            },
        )

    async def bury(self, pending: PendingEvent, last_status: int) -> None:
        await self._dead.insert_one(
            {
                "event_id": pending.event_id,
                "event_bytes": pending.event_bytes,
                "occurred_at": pending.occurred_at,
                "attempts": pending.attempts + 1,
                "last_status": last_status,
                "created_at": pending.created_at,
                "buried_at": datetime.now(UTC),
            }
        )
        await self._col.delete_one({"_id": pending.id})

    async def pending_count(self) -> int:
        return await self._col.count_documents({})

    async def oldest_pending_age_seconds(self) -> float:
        document = await self._col.find_one({}, sort=[("created_at", ASCENDING)])
        if document is None:
            return 0.0
        return (datetime.now(UTC) - document["created_at"]).total_seconds()
