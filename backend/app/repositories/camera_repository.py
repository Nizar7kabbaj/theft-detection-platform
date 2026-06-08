from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection

from app.repositories.base import BaseRepository


class CameraRepository(BaseRepository[dict[str, Any]]):
    def __init__(self, collection: AsyncIOMotorCollection) -> None:
        super().__init__(collection)

    async def find_by_name(self, name: str) -> dict[str, Any] | None:
        return await self._col.find_one({"name": name})
