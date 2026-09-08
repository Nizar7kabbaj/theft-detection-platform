from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection

from app.repositories.base import BaseRepository


class PolicyRepository(BaseRepository[dict[str, Any]]):
    def __init__(self, collection: AsyncIOMotorCollection) -> None:
        super().__init__(collection)

    async def current(self) -> dict[str, Any] | None:
        return await self._col.find_one(sort=[("version", -1)])

    async def append(self, document: dict[str, Any]) -> dict[str, Any] | None:
        await self._col.insert_one(document)
        return await self._col.find_one({"version": document["version"]})

    async def history(self, limit: int = 20) -> list[dict[str, Any]]:
        cursor = self._col.find({}, sort=[("version", -1)]).limit(limit)
        return await cursor.to_list(length=limit)
