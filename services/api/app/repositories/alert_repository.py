from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection

from app.repositories.base import BaseRepository


class AlertRepository(BaseRepository[dict[str, Any]]):
    def __init__(self, collection: AsyncIOMotorCollection) -> None:
        super().__init__(collection)

    async def list_filtered(
        self, severity: str | None = None, limit: int = 50, skip: int = 0
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {}
        if severity:
            query["severity"] = severity
        return await self.list(
            query=query, limit=limit, skip=skip, sort=[("created_at", -1)]
        )

    async def acknowledge(self, id_: str) -> dict[str, Any] | None:
        return await self.update(
            id_, {"acknowledged": True, "acknowledged_at": datetime.now(timezone.utc)}
        )
