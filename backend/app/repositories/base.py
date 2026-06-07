"""generic mongo repository. one create/get/list/update/delete/count for every collection."""

from typing import Any, Generic, TypeVar

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorCollection

from app.core.errors import ValidationError

T = TypeVar("T")


class BaseRepository(Generic[T]):
    def __init__(self, collection: AsyncIOMotorCollection) -> None:
        self._col = collection

    @staticmethod
    def _oid(value: str) -> ObjectId:
        try:
            return ObjectId(value)
        except InvalidId as exc:
            raise ValidationError(f"malformed id: {value}") from exc

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        result = await self._col.insert_one(data)
        return await self._col.find_one({"_id": result.inserted_id})

    async def get(self, id_: str) -> dict[str, Any] | None:
        return await self._col.find_one({"_id": self._oid(id_)})

    async def list(
        self,
        query: dict[str, Any] | None = None,
        limit: int = 100,
        skip: int = 0,
        sort: list[tuple[str, int]] | None = None,
    ) -> list[dict[str, Any]]:
        cursor = self._col.find(query or {})
        if sort:
            cursor = cursor.sort(sort)
        cursor = cursor.skip(skip).limit(limit)
        return await cursor.to_list(length=limit)

    async def update(self, id_: str, changes: dict[str, Any]) -> dict[str, Any] | None:
        return await self._col.find_one_and_update(
            {"_id": self._oid(id_)},
            {"$set": changes},
            return_document=True,
        )

    async def delete(self, id_: str) -> bool:
        result = await self._col.delete_one({"_id": self._oid(id_)})
        return result.deleted_count == 1

    async def count(self, query: dict[str, Any] | None = None) -> int:
        return await self._col.count_documents(query or {})
