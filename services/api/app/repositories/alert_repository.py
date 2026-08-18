from datetime import UTC, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection

from app.repositories.base import BaseRepository


class AlertRepository(BaseRepository[dict[str, Any]]):
    def __init__(self, collection: AsyncIOMotorCollection) -> None:
        super().__init__(collection)

    async def list_page(
        self,
        severity: str | None = None,
        acknowledged: bool | None = None,
        limit: int = 51,
        after: tuple[datetime, str] | None = None,
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {}
        if severity:
            query["severity"] = severity
        if acknowledged is not None:
            query["acknowledged"] = acknowledged
        if after is not None:
            created_at, id_ = after
            query["$or"] = [
                {"created_at": {"$lt": created_at}},
                {"created_at": created_at, "_id": {"$lt": self._oid(id_)}},
            ]
        cursor = self._col.find(query).sort([("created_at", -1), ("_id", -1)]).limit(limit)
        return await cursor.to_list(length=limit)

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
