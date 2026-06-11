from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from redis.asyncio import Redis

from app.core.cache import get_or_set, invalidate_prefix, make_list_key
from app.core.errors import AlertUnavailable, NotFoundError
from app.repositories.alert_repository import AlertRepository
from app.schemas.alert import AlertCreate, AlertResponse
from app.services.alert_service import AlertClient

logger = logging.getLogger(__name__)


def _to_response(doc: dict[str, Any]) -> AlertResponse:
    obj = doc.get("object") or {}
    alert_type = doc.get("alert_type", "object_proximity")

    if obj:
        object_name = obj.get("class_name", "unknown")
        confidence = obj.get("confidence")
    else:
        object_name = "person bending" if alert_type == "bending" else alert_type
        confidence = None

    return AlertResponse.model_validate(
        {
            "_id": doc["_id"],
            "alert_id": doc["alert_id"],
            "session_id": doc["session_id"],
            "timestamp": doc["timestamp"],
            "camera_id": doc["camera_id"],
            "severity": doc["severity"],
            "object_name": object_name,
            "confidence": confidence,
            "snapshot_url": doc.get("snapshot_path"),
            "alert_type": alert_type,
        }
    )


class AlertUseCase:
    LIST_PREFIX = "cache:alerts:list:"
    TTL = 30

    def __init__(
        self,
        repo: AlertRepository,
        redis: Redis,
        alert_client: AlertClient,
    ) -> None:
        self._repo = repo
        self._redis = redis
        self._alert_client = alert_client

    async def create(self, payload: AlertCreate) -> AlertResponse:
        doc = payload.model_dump()
        doc["created_at"] = datetime.now(timezone.utc)
        doc["acknowledged"] = False
        created = await self._repo.create(doc)

        try:
            await self._alert_client.send(payload)
        except AlertUnavailable as exc:
            logger.warning("alert delivery unavailable for %s: %s", payload.alert_id, exc)

        await invalidate_prefix(self._redis, self.LIST_PREFIX)
        return _to_response(created)

    async def list(
        self, severity: str | None = None, limit: int = 50, skip: int = 0
    ) -> list[AlertResponse]:
        params = {"severity": severity, "limit": limit, "skip": skip}
        key = make_list_key("alerts", params)

        async def loader() -> list[dict]:
            docs = await self._repo.list_filtered(severity=severity, limit=limit, skip=skip)
            return [_to_response(d).model_dump(mode="json") for d in docs]

        cached = await get_or_set(self._redis, key, self.TTL, loader)
        return [AlertResponse.model_validate(item) for item in cached]

    async def acknowledge(self, alert_id: str) -> AlertResponse:
        updated = await self._repo.acknowledge(alert_id)
        if updated is None:
            raise NotFoundError(f"alert {alert_id} not found")
        await invalidate_prefix(self._redis, self.LIST_PREFIX)
        return _to_response(updated)

    async def delete(self, alert_id: str) -> None:
        deleted = await self._repo.delete(alert_id)
        if not deleted:
            raise NotFoundError(f"alert {alert_id} not found")
        await invalidate_prefix(self._redis, self.LIST_PREFIX)
