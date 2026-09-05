from __future__ import annotations

from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo import ASCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.repositories.base import BaseRepository
from app.shared.schemas.delivery import (
    Channel,
    DeliveryIntent,
    DeliveryIntentCreate,
    DeliverySource,
    DeliveryStatus,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class DeliveryIntentRepository(BaseRepository[DeliveryIntent]):
    def __init__(self, collection: AsyncIOMotorCollection) -> None:
        super().__init__(collection)

    @staticmethod
    def _natural_key(
        source: DeliverySource,
        source_ref: str,
        channel: Channel,
        recipient: str,
    ) -> dict[str, str]:
        return {
            "source": source.value,
            "source_ref": source_ref,
            "channel": channel.value,
            "recipient": recipient,
        }

    @staticmethod
    def _to_model(doc: dict) -> DeliveryIntent:
        return DeliveryIntent.model_validate(doc)

    async def acquire(self, intent: DeliveryIntentCreate) -> DeliveryIntent:
        doc = intent.model_dump(mode="python")
        try:
            result = await self._col.insert_one(doc)
            fresh = await self._col.find_one({"_id": result.inserted_id})
            return self._to_model(fresh)
        except DuplicateKeyError:
            existing = await self._col.find_one(
                self._natural_key(
                    intent.source, intent.source_ref, intent.channel, intent.recipient
                )
            )
            return self._to_model(existing)

    async def get_by_id(self, intent_id: str) -> DeliveryIntent | None:
        doc = await self._col.find_one({"_id": self._oid(intent_id)})
        return self._to_model(doc) if doc else None

    async def list_by_source_ref(
        self,
        source: DeliverySource,
        source_ref: str,
    ) -> list[DeliveryIntent]:
        cursor = self._col.find({"source": source.value, "source_ref": source_ref}).sort(
            "created_at", 1
        )
        return [self._to_model(doc) async for doc in cursor]

    async def list_by_source_refs(
        self,
        source: DeliverySource,
        source_refs: list[str],
    ) -> list[DeliveryIntent]:
        if not source_refs:
            return []
        cursor = self._col.find({"source": source.value, "source_ref": {"$in": source_refs}}).sort(
            "created_at", 1
        )
        return [self._to_model(doc) async for doc in cursor]

    async def mark_sending(self, intent_id: str) -> DeliveryIntent | None:
        now = _utcnow()
        doc = await self._col.find_one_and_update(
            {
                "_id": self._oid(intent_id),
                "status": {"$nin": [DeliveryStatus.SENT.value, DeliveryStatus.DEAD.value]},
            },
            {
                "$set": {
                    "status": DeliveryStatus.SENDING.value,
                    "attempt_started_at": now,
                    "updated_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return self._to_model(doc) if doc else None

    async def mark_sent(self, intent_id: str) -> DeliveryIntent | None:
        now = _utcnow()
        doc = await self._col.find_one_and_update(
            {"_id": self._oid(intent_id)},
            {
                "$set": {
                    "status": DeliveryStatus.SENT.value,
                    "attempt_started_at": None,
                    "updated_at": now,
                },
                "$inc": {"attempts": 1},
            },
            return_document=ReturnDocument.AFTER,
        )
        return self._to_model(doc) if doc else None

    async def mark_failed(self, intent_id: str, last_error: str) -> DeliveryIntent | None:
        now = _utcnow()
        doc = await self._col.find_one_and_update(
            {"_id": self._oid(intent_id)},
            {
                "$set": {
                    "status": DeliveryStatus.FAILED.value,
                    "attempt_started_at": None,
                    "last_error": last_error,
                    "updated_at": now,
                },
                "$inc": {"attempts": 1},
            },
            return_document=ReturnDocument.AFTER,
        )
        return self._to_model(doc) if doc else None

    async def mark_dead(self, intent_id: str, last_error: str) -> DeliveryIntent | None:
        now = _utcnow()
        doc = await self._col.find_one_and_update(
            {"_id": self._oid(intent_id)},
            {
                "$set": {
                    "status": DeliveryStatus.DEAD.value,
                    "attempt_started_at": None,
                    "last_error": last_error,
                    "updated_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return self._to_model(doc) if doc else None

    async def mark_buffered(self, intent_id: str, last_error: str) -> DeliveryIntent | None:
        now = _utcnow()
        doc = await self._col.find_one_and_update(
            {
                "_id": self._oid(intent_id),
                "status": {"$nin": [DeliveryStatus.SENT.value, DeliveryStatus.DEAD.value]},
            },
            {
                "$set": {
                    "status": DeliveryStatus.BUFFERED.value,
                    "attempt_started_at": None,
                    "last_error": last_error,
                    "updated_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return self._to_model(doc) if doc else None

    async def release_buffered(self, limit: int = 100) -> list[DeliveryIntent]:
        released: list[DeliveryIntent] = []
        for _ in range(limit):
            now = _utcnow()
            doc = await self._col.find_one_and_update(
                {"status": DeliveryStatus.BUFFERED.value},
                {
                    "$set": {
                        "status": DeliveryStatus.PENDING.value,
                        "updated_at": now,
                    }
                },
                sort=[("created_at", ASCENDING)],
                return_document=ReturnDocument.AFTER,
            )
            if doc is None:
                break
            released.append(self._to_model(doc))
        return released

    async def mark_requeued(self, intent_id: str, cutoff: datetime) -> DeliveryIntent | None:
        now = _utcnow()
        doc = await self._col.find_one_and_update(
            {
                "_id": self._oid(intent_id),
                "status": {
                    "$in": [
                        DeliveryStatus.PENDING.value,
                        DeliveryStatus.SENDING.value,
                    ]
                },
                "updated_at": {"$lt": cutoff},
            },
            {
                "$set": {
                    "status": DeliveryStatus.PENDING.value,
                    "attempt_started_at": None,
                    "updated_at": now,
                },
                "$inc": {"requeue_count": 1},
            },
            return_document=ReturnDocument.AFTER,
        )
        return self._to_model(doc) if doc else None

    async def find_stale(
        self, status: DeliveryStatus, cutoff: datetime, limit: int = 100
    ) -> list[DeliveryIntent]:
        cursor = self._col.find({"status": status.value, "updated_at": {"$lt": cutoff}}).limit(
            limit
        )
        docs = await cursor.to_list(length=limit)
        return [self._to_model(doc) for doc in docs]
