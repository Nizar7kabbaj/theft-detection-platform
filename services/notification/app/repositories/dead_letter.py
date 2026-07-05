from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorCollection

from app.repositories.base import BaseRepository
from app.shared.schemas.delivery import DeadLetter, DeadLetterCreate


class DeadLetterRepository(BaseRepository[DeadLetter]):
    def __init__(self, collection: AsyncIOMotorCollection) -> None:
        super().__init__(collection)

    @staticmethod
    def _to_model(doc: dict) -> DeadLetter:
        return DeadLetter.model_validate(doc)

    async def create(self, entry: DeadLetterCreate) -> DeadLetter:
        doc = entry.model_dump(mode="python")
        result = await self._col.insert_one(doc)
        fresh = await self._col.find_one({"_id": result.inserted_id})
        return self._to_model(fresh)

    async def find_by_intent_id(self, intent_id: str) -> DeadLetter | None:
        doc = await self._col.find_one({"intent_id": intent_id})
        return self._to_model(doc) if doc else None
