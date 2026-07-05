from __future__ import annotations

from typing import Generic, TypeVar

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorCollection

T = TypeVar("T")


class BaseRepository(Generic[T]):
    def __init__(self, collection: AsyncIOMotorCollection) -> None:
        self._col = collection

    @staticmethod
    def _oid(value: str) -> ObjectId:
        try:
            return ObjectId(value)
        except InvalidId as exc:
            raise ValueError(f"malformed id: {value}") from exc
