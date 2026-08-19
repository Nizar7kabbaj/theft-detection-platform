from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection

from app.repositories.base import BaseRepository


class CameraRepository(BaseRepository[dict[str, Any]]):
    def __init__(self, collection: AsyncIOMotorCollection) -> None:
        super().__init__(collection)

    async def find_by_name(self, name: str) -> dict[str, Any] | None:
        return await self._col.find_one({"name": name})

    async def get(self, id_: str) -> dict[str, Any] | None:
        return await self._col.find_one({"camera_id": id_})

    async def delete(self, id_: str) -> bool:
        result = await self._col.delete_one({"camera_id": id_})
        return result.deleted_count == 1
