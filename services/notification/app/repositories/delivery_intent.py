from __future__ import annotations

from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo import ReturnDocument
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
    return datetime.now(timezone.utc)


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

    async def mark_sending(self, intent_id: str) -> DeliveryIntent | None:
        now = _utcnow()
        doc = await self._col.find_one_and_update(
            {
                "_id": self._oid(intent_id),
                "status": {
                    "$nin": [DeliveryStatus.SENT.value, DeliveryStatus.DEAD.value]
                },
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

    async def mark_failed(
        self, intent_id: str, last_error: str
    ) -> DeliveryIntent | None:
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

    async def mark_dead(
        self, intent_id: str, last_error: str
    ) -> DeliveryIntent | None:
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

    async def find_stale(
        self, status: DeliveryStatus, cutoff: datetime, limit: int = 100
    ) -> list[DeliveryIntent]:
        cursor = self._col.find(
            {"status": status.value, "updated_at": {"$lt": cutoff}}
        ).limit(limit)
        docs = await cursor.to_list(length=limit)
        return [self._to_model(doc) for doc in docs]
