from datetime import UTC, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

BUCKET_UNITS = {"hour": "hour", "day": "day"}


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

    async def count_by_severity(self, severities: list[str]) -> int:
        return await self._db.alerts.count_documents({"severity": {"$in": severities}})

    async def top_objects(self, limit: int = 5) -> list[dict[str, Any]]:
        pipeline = [
            {"$match": {"object.class_name": {"$type": "string", "$ne": ""}}},
            {"$group": {"_id": "$object.class_name", "count": {"$sum": 1}}},
            {"$sort": {"count": -1, "_id": 1}},
            {"$limit": limit},
        ]
        results: list[dict[str, Any]] = []
        async for doc in self._db.alerts.aggregate(pipeline):
            results.append({"object": doc["_id"], "count": doc["count"]})
        return results

    async def alerts_over_time(
        self,
        start: datetime,
        end: datetime,
        unit: str,
    ) -> list[dict[str, Any]]:
        pipeline = [
            {"$match": {"created_at": {"$gte": start, "$lt": end}}},
            {
                "$group": {
                    "_id": {
                        "bucket": {
                            "$dateTrunc": {
                                "date": "$created_at",
                                "unit": BUCKET_UNITS[unit],
                                "timezone": "UTC",
                            }
                        },
                        "severity": "$severity",
                    },
                    "count": {"$sum": 1},
                }
            },
            {"$sort": {"_id.bucket": 1}},
        ]
        results: list[dict[str, Any]] = []
        async for doc in self._db.alerts.aggregate(pipeline):
            results.append(
                {
                    "bucket": doc["_id"]["bucket"],
                    "severity": doc["_id"]["severity"],
                    "count": doc["count"],
                }
            )
        return results

    async def decisions_over_time(
        self,
        start: datetime,
        end: datetime,
        unit: str,
    ) -> list[dict[str, Any]]:
        pipeline = [
            {
                "$match": {
                    "decided_at": {"$type": "date", "$gte": start, "$lt": end},
                }
            },
            {
                "$group": {
                    "_id": {
                        "bucket": {
                            "$dateTrunc": {
                                "date": "$decided_at",
                                "unit": BUCKET_UNITS[unit],
                                "timezone": "UTC",
                            }
                        },
                        "decision": "$decision",
                    },
                    "count": {"$sum": 1},
                }
            },
            {"$sort": {"_id.bucket": 1}},
        ]
        results: list[dict[str, Any]] = []
        async for doc in self._db.alerts.aggregate(pipeline):
            results.append(
                {
                    "bucket": doc["_id"]["bucket"],
                    "decision": doc["_id"]["decision"],
                    "count": doc["count"],
                }
            )
        return results
