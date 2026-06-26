from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection

from app.repositories.base import BaseRepository


class DetectionRepository(BaseRepository[dict[str, Any]]):
    def __init__(self, collection: AsyncIOMotorCollection) -> None:
        super().__init__(collection)

    async def list_recent(self, limit: int = 50, skip: int = 0) -> list[dict[str, Any]]:
        return await self.list(limit=limit, skip=skip, sort=[("created_at", -1)])

    async def list_by_session(self, session_id: int) -> list[dict[str, Any]]:
        return await self.list(query={"session_id": session_id}, limit=200)
