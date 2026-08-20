from __future__ import annotations

import base64
import binascii
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import anyio.to_thread
from redis.asyncio import Redis

from app.core.cache import get_or_set, invalidate, invalidate_prefix, make_list_key
from app.core.config import settings
from app.core.errors import AlertUnavailableError, NotFoundError, ValidationError
from app.repositories.alert_repository import SORT_CREATED, SORT_DECIDED, AlertRepository
from app.schemas.alert import (
    AlertCreate,
    AlertDetail,
    AlertPage,
    AlertResponse,
    AlertSort,
    AlertType,
    Decision,
    Severity,
)
from app.services.alert_service import AlertClient
from app.services.audit_service import AuditClient

logger = logging.getLogger(__name__)

_CURSOR_SEGMENTS = 3


def _readable_alert_type(alert_type: str | None) -> str:
    if alert_type is None:
        return "unspecified"
    return alert_type.replace("ALERT_TYPE_", "").lower().replace("_", " ")


def encode_cursor(sort: str, boundary: datetime, id_: str) -> str:
    raw = f"{sort}|{boundary.astimezone(UTC).isoformat()}|{id_}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def decode_cursor(cursor: str, sort: str) -> tuple[datetime, str]:
    padded = cursor + "=" * (-len(cursor) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise ValidationError("malformed cursor") from exc
    parts = raw.split("|")
    if len(parts) != _CURSOR_SEGMENTS:
        raise ValidationError("malformed cursor")
    origin, timestamp, id_ = parts
    if not id_ or not timestamp:
        raise ValidationError("malformed cursor")
    if origin != sort:
        raise ValidationError("cursor does not match the requested order")
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError as exc:
        raise ValidationError("malformed cursor") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed, id_


def _snapshot_url(doc: dict[str, Any]) -> str | None:
    if not (doc.get("snapshot_path") or doc.get("snapshot_url")):
        return None
    return f"/api/v1/alerts/{doc['_id']}/snapshot"


def _resolve_snapshot(root_dir: str, stored: str) -> Path | None:
    root = Path(root_dir).resolve()
    candidate = (root / Path(stored).name).resolve()
    if candidate.parent != root or not candidate.is_file():
        return None
    return candidate


def _to_response(doc: dict[str, Any]) -> AlertResponse:
    obj = doc.get("object") or {}
    alert_type = doc.get("alert_type") or AlertType.ALERT_TYPE_UNSPECIFIED.value
    object_name = obj.get("class_name") or doc.get("object_name")
    if not object_name:
        object_name = _readable_alert_type(alert_type)
    confidence = obj.get("confidence")
    if confidence is None:
        confidence = doc.get("confidence")
    created_at = doc.get("created_at") or doc["occurred_at"]
    return AlertResponse.model_validate(
        {
            "_id": doc["_id"],
            "alert_id": doc["alert_id"],
            "session_id": doc["session_id"],
            "occurred_at": doc["occurred_at"],
            "created_at": created_at,
            "camera_id": doc["camera_id"],
            "severity": doc["severity"],
            "object_name": object_name,
            "confidence": confidence,
            "snapshot_url": _snapshot_url(doc),
            "alert_type": alert_type,
            "acknowledged": bool(doc.get("acknowledged", False)),
            "acknowledged_at": doc.get("acknowledged_at"),
            "decision": doc.get("decision") or Decision.DECISION_UNSPECIFIED.value,
            "decided_at": doc.get("decided_at"),
            "decided_by": doc.get("decided_by"),
        }
    )


def _to_detail(doc: dict[str, Any]) -> AlertDetail:
    return AlertDetail.model_validate(
        {
            "_id": doc["_id"],
            "alert_id": doc["alert_id"],
            "session_id": doc["session_id"],
            "frame_index": doc.get("frame_index", 0),
            "occurred_at": doc["occurred_at"],
            "created_at": doc.get("created_at") or doc["occurred_at"],
            "camera_id": doc["camera_id"],
            "severity": doc["severity"],
            "alert_type": doc.get("alert_type") or AlertType.ALERT_TYPE_UNSPECIFIED.value,
            "acknowledged": bool(doc.get("acknowledged", False)),
            "acknowledged_at": doc.get("acknowledged_at"),
            "decision": doc.get("decision") or Decision.DECISION_UNSPECIFIED.value,
            "decided_at": doc.get("decided_at"),
            "decided_by": doc.get("decided_by"),
            "person": doc.get("person"),
            "object": doc.get("object"),
            "frame_width": doc.get("frame_width"),
            "frame_height": doc.get("frame_height"),
            "concealment": doc.get("concealment"),
            "classifier_score": doc.get("classifier_score"),
            "classifier_state": doc.get("classifier_state"),
            "snapshot_url": _snapshot_url(doc),
        }
    )


class AlertUseCase:
    LIST_PREFIX = "cache:alerts:list:"
    CAMERA_FACET_KEY = "cache:alerts:cameras"
    TTL = 30
    FACET_TTL = 300

    def __init__(
        self,
        repo: AlertRepository,
        redis: Redis,
        alert_client: AlertClient,
        audit_client: AuditClient,
    ) -> None:
        self._repo = repo
        self._redis = redis
        self._alert_client = alert_client
        self._audit = audit_client

    async def _publish(self, event: str, response: AlertResponse) -> None:
        try:
            payload = response.model_dump_json(by_alias=True)
            await self._redis.publish(f"alerts:{event}", payload)
        except Exception as exc:
            logger.warning("pubsub publish failed event=%s: %s", event, exc)

    async def create(self, payload: AlertCreate) -> AlertResponse:
        doc = payload.model_dump(mode="json")
        doc["occurred_at"] = payload.occurred_at
        doc["created_at"] = datetime.now(UTC)
        doc["acknowledged"] = False
        doc["decision"] = Decision.DECISION_UNSPECIFIED.value
        created = await self._repo.create(doc)
        try:
            await self._alert_client.send(payload)
        except AlertUnavailableError as exc:
            logger.warning("alert delivery unavailable for %s: %s", payload.alert_id, exc)
        await invalidate_prefix(self._redis, self.LIST_PREFIX)
        await invalidate(self._redis, self.CAMERA_FACET_KEY)
        response = _to_response(created)
        await self._publish("created", response)
        return response

    async def list(
        self,
        severity: Severity | None = None,
        acknowledged: bool | None = None,
        decision: Decision | None = None,
        camera_id: str | None = None,
        sort: AlertSort = AlertSort.CREATED_AT,
        limit: int = 50,
        cursor: str | None = None,
    ) -> AlertPage:
        order = SORT_DECIDED if sort is AlertSort.DECIDED_AT else SORT_CREATED
        after = decode_cursor(cursor, order) if cursor else None
        params = {
            "severity": severity.value if severity else None,
            "acknowledged": acknowledged,
            "decision": decision.value if decision else None,
            "camera_id": camera_id,
            "sort": order,
            "limit": limit,
            "cursor": cursor,
        }
        key = make_list_key("alerts", params)

        async def loader() -> dict[str, Any]:
            docs = await self._repo.list_page(
                severity=severity.value if severity else None,
                acknowledged=acknowledged,
                decision=decision.value if decision else None,
                camera_id=camera_id,
                sort=order,
                limit=limit + 1,
                after=after,
            )
            has_more = len(docs) > limit
            page = docs[:limit]
            items = [_to_response(d).model_dump(mode="json", by_alias=True) for d in page]
            next_cursor = None
            if has_more and page:
                last = page[-1]
                boundary = last.get(order)
                if boundary is not None:
                    next_cursor = encode_cursor(order, boundary, str(last["_id"]))
            return {"items": items, "next_cursor": next_cursor}

        cached = await get_or_set(self._redis, key, self.TTL, loader)
        return AlertPage.model_validate(cached)

    async def camera_facet(self) -> list[str]:
        async def loader() -> list[str]:
            return await self._repo.distinct_cameras()

        cached = await get_or_set(self._redis, self.CAMERA_FACET_KEY, self.FACET_TTL, loader)
        return [str(value) for value in cached]

    async def get(self, alert_id: str) -> AlertDetail:
        doc = await self._repo.get(alert_id)
        if doc is None:
            raise NotFoundError(f"alert {alert_id} not found")
        return _to_detail(doc)

    async def snapshot_path(self, alert_id: str) -> Path:
        doc = await self._repo.get(alert_id)
        if doc is None:
            raise NotFoundError(f"alert {alert_id} not found")
        stored = doc.get("snapshot_path")
        if not stored:
            raise NotFoundError(f"alert {alert_id} has no snapshot")
        resolved = await anyio.to_thread.run_sync(_resolve_snapshot, settings.SNAPSHOTS_DIR, stored)
        if resolved is None:
            raise NotFoundError(f"alert {alert_id} has no snapshot")
        return resolved

    async def acknowledge(self, alert_id: str, actor_id: str) -> AlertResponse:
        updated, acked_now = await self._repo.acknowledge(alert_id)
        if updated is None:
            raise NotFoundError(f"alert {alert_id} not found")
        response = _to_response(updated)
        if acked_now:
            await invalidate_prefix(self._redis, self.LIST_PREFIX)
            await self._publish("acknowledged", response)
            await self._audit.emit_alert_acknowledged(
                alert_id=str(updated["_id"]),
                actor_user_id=actor_id,
            )
        return response

    async def decide(self, alert_id: str, decision: Decision, actor_id: str) -> AlertDetail:
        updated, changed = await self._repo.decide(alert_id, decision.value, actor_id)
        if updated is None:
            raise NotFoundError(f"alert {alert_id} not found")
        if changed:
            await invalidate_prefix(self._redis, self.LIST_PREFIX)
            await self._publish("decided", _to_response(updated))
            await self._audit.emit_alert_acknowledged(
                alert_id=str(updated["_id"]),
                actor_user_id=actor_id,
            )
        return _to_detail(updated)
