from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings

BUCKET_UNITS = {"hour": "hour", "day": "day"}
STORE_ZONE = ZoneInfo(settings.STORE_TIME_ZONE)
MINUTE_SECONDS = 60
FIVE_MINUTES_SECONDS = 300
FIFTEEN_MINUTES_SECONDS = 900


def store_day_start() -> datetime:
    return datetime.now(STORE_ZONE).replace(hour=0, minute=0, second=0, microsecond=0)


def _count_between(low: int | None, high: int | None) -> dict[str, Any]:
    bounds: list[dict[str, Any]] = []
    if low is not None:
        bounds.append({"$gte": ["$seconds", low]})
    if high is not None:
        bounds.append({"$lt": ["$seconds", high]})
    return {"$sum": {"$cond": [{"$and": bounds}, 1, 0]}}


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
        return await self._db.alerts.count_documents({"created_at": {"$gte": store_day_start()}})

    async def count_by_severity(self, severities: list[str], since: datetime | None = None) -> int:
        query: dict[str, Any] = {"severity": {"$in": severities}}
        if since is not None:
            query["created_at"] = {"$gte": since}
        return await self._db.alerts.count_documents(query)

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
                                "timezone": settings.STORE_TIME_ZONE,
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
                                "timezone": settings.STORE_TIME_ZONE,
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

    async def created_breakdown(self, start: datetime, end: datetime) -> dict[str, Any]:
        pipeline = [
            {"$match": {"created_at": {"$gte": start, "$lt": end}}},
            {
                "$facet": {
                    "raised": [{"$count": "count"}],
                    "cameras": [{"$group": {"_id": "$camera_id", "count": {"$sum": 1}}}],
                    "alert_types": [{"$group": {"_id": "$alert_type", "count": {"$sum": 1}}}],
                }
            },
        ]
        async for doc in self._db.alerts.aggregate(pipeline):
            raised = doc["raised"][0]["count"] if doc["raised"] else 0
            return {
                "raised": raised,
                "cameras": doc["cameras"],
                "alert_types": doc["alert_types"],
            }
        return {"raised": 0, "cameras": [], "alert_types": []}

    async def decided_breakdown(self, start: datetime, end: datetime) -> dict[str, Any]:
        pipeline = [
            {"$match": {"decided_at": {"$type": "date", "$gte": start, "$lt": end}}},
            {
                "$project": {
                    "_id": 0,
                    "seconds": {
                        "$dateDiff": {
                            "startDate": "$created_at",
                            "endDate": "$decided_at",
                            "unit": "second",
                        }
                    },
                }
            },
            {
                "$group": {
                    "_id": None,
                    "decided": {"$sum": 1},
                    "median": {"$median": {"input": "$seconds", "method": "approximate"}},
                    "under_60": _count_between(None, MINUTE_SECONDS),
                    "under_300": _count_between(MINUTE_SECONDS, FIVE_MINUTES_SECONDS),
                    "under_900": _count_between(FIVE_MINUTES_SECONDS, FIFTEEN_MINUTES_SECONDS),
                    "over_900": _count_between(FIFTEEN_MINUTES_SECONDS, None),
                }
            },
        ]
        async for doc in self._db.alerts.aggregate(pipeline):
            return doc
        return {
            "decided": 0,
            "median": None,
            "under_60": 0,
            "under_300": 0,
            "under_900": 0,
            "over_900": 0,
        }
