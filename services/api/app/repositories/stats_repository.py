from datetime import UTC, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase


class StatsRepository:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._db = db

    async def count_alerts(self) -> int:
        return await self._db.alerts.count_documents({})

    async def count_detections(self) -> int:
        return await self._db.detections.count_documents({})

    async def count_cameras(self) -> int:
        return await self._db.cameras.count_documents({})

    async def count_alerts_today(self) -> int:
        start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        return await self._db.alerts.count_documents({"created_at": {"$gte": start}})

    async def count_by_severity(self, severity: str) -> int:
        return await self._db.alerts.count_documents({"severity": severity})

    async def top_objects(self, limit: int = 5) -> list[dict[str, Any]]:
        pipeline = [
            {"$group": {"_id": "$object.class_name", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": limit},
        ]
        results: list[dict[str, Any]] = []
        async for doc in self._db.alerts.aggregate(pipeline):
            results.append({"object": doc["_id"], "count": doc["count"]})
        return results
