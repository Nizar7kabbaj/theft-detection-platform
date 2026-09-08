from datetime import UTC, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection

from app.repositories.base import BaseRepository

SORT_CREATED = "created_at"
SORT_DECIDED = "decided_at"


class AlertRepository(BaseRepository[dict[str, Any]]):
    def __init__(self, collection: AsyncIOMotorCollection) -> None:
        super().__init__(collection)

    async def list_page(
        self,
        severity: str | None = None,
        acknowledged: bool | None = None,
        decision: str | None = None,
        camera_id: str | None = None,
        sort: str = SORT_CREATED,
        limit: int = 51,
        after: tuple[datetime, str] | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        field = SORT_DECIDED if sort == SORT_DECIDED else SORT_CREATED
        query = self._build_query(
            field=field,
            severity=severity,
            acknowledged=acknowledged,
            decision=decision,
            camera_id=camera_id,
            start=start,
            end=end,
        )
        if after is not None:
            boundary, id_ = after
            page_clause = [
                {field: {"$lt": boundary}},
                {field: boundary, "_id": {"$lt": self._oid(id_)}},
            ]
            existing = query.pop("$and", [])
            query["$and"] = [*existing, {"$or": page_clause}]
        cursor = self._col.find(query).sort([(field, -1), ("_id", -1)]).limit(limit)
        return await cursor.to_list(length=limit)

    def _build_query(
        self,
        field: str,
        severity: str | None,
        acknowledged: bool | None,
        decision: str | None,
        camera_id: str | None,
        start: datetime | None,
        end: datetime | None,
    ) -> dict[str, Any]:
        query: dict[str, Any] = {}
        if severity:
            query["severity"] = severity
        if acknowledged is not None:
            query["acknowledged"] = acknowledged
        if decision:
            query["decision"] = decision
        if camera_id:
            query["camera_id"] = camera_id
        field_clause: dict[str, Any] = {}
        if field == SORT_DECIDED:
            field_clause["$type"] = "date"
        if start is not None:
            field_clause["$gte"] = start
        if end is not None:
            field_clause["$lte"] = end
        if field_clause:
            query[field] = field_clause
        return query

    async def count(
        self,
        severity: str | None = None,
        acknowledged: bool | None = None,
        decision: str | None = None,
        camera_id: str | None = None,
        sort: str = SORT_CREATED,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> int:
        field = SORT_DECIDED if sort == SORT_DECIDED else SORT_CREATED
        query = self._build_query(
            field=field,
            severity=severity,
            acknowledged=acknowledged,
            decision=decision,
            camera_id=camera_id,
            start=start,
            end=end,
        )
        return await self._col.count_documents(query)

    async def distinct_cameras(self) -> list[str]:
        values = await self._col.distinct("camera_id")
        return sorted(v for v in values if isinstance(v, str) and v)

    async def acknowledge(self, id_: str) -> tuple[dict[str, Any] | None, bool]:
        result = await self._col.update_one(
            {"_id": self._oid(id_), "acknowledged": {"$ne": True}},
            {"$set": {"acknowledged": True, "acknowledged_at": datetime.now(UTC)}},
        )
        if result.matched_count == 1:
            doc = await self.get(id_)
            return doc, True
        doc = await self.get(id_)
        return doc, False

    async def decide(
        self,
        id_: str,
        decision: str,
        actor_id: str,
    ) -> tuple[dict[str, Any] | None, bool]:
        oid = self._oid(id_)
        changes: dict[str, Any] = {"decision": decision}
        if decision == "DECISION_UNSPECIFIED":
            changes["decided_at"] = None
            changes["decided_by"] = None
        else:
            changes["decided_at"] = datetime.now(UTC)
            changes["decided_by"] = actor_id
        updated = await self._col.find_one_and_update(
            {"_id": oid, "decision": {"$ne": decision}},
            {"$set": changes},
            return_document=True,
        )
        if updated is not None:
            return updated, True
        return await self.get(id_), False
