from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from opentelemetry import context as otel_context
from opentelemetry import trace
from redis.asyncio import Redis

from app.core.cache import get_or_set, invalidate_prefix, make_list_key
from app.core.errors import NotFoundError
from app.repositories.alert_repository import AlertRepository
from app.schemas.alert import AlertCreate, AlertResponse
from app.services import telegram_service

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("backend.alert")

_background_tasks: set[asyncio.Task[None]] = set()


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


def _build_telegram_text(payload: AlertCreate) -> str:
    if payload.alert_type == "bending":
        what = "person bending, possible concealment"
    elif payload.object:
        what = f"person near {payload.object.get('class_name', 'object')}"
    else:
        what = payload.alert_type or "suspicious activity"
    angle_line = ""
    if payload.torso_angle is not None:
        angle_line = f"\ntorso angle: <b>{payload.torso_angle:.1f}°</b>"
    return (
        f"<b>theft-detection alert, {payload.severity}</b>\n"
        f"{what}\n"
        f"camera: <code>{payload.camera_id}</code>\n"
        f"time: {payload.timestamp}"
        f"{angle_line}"
    )


async def _notify(payload: AlertCreate) -> None:
    with tracer.start_as_current_span("telegram_notify") as span:
        span.set_attribute("alert.id", payload.alert_id)
        span.set_attribute("alert.severity", payload.severity)
        text = _build_telegram_text(payload)
        snapshot = payload.snapshot_path
        if snapshot:
            sent = await asyncio.to_thread(telegram_service.send_photo, snapshot, text)
            if not sent:
                await asyncio.to_thread(telegram_service.send_message, text)
        else:
            await asyncio.to_thread(telegram_service.send_message, text)


def _spawn_notify(payload: AlertCreate) -> None:
    ctx = otel_context.get_current()

    async def runner() -> None:
        token = otel_context.attach(ctx)
        try:
            await _notify(payload)
        except Exception as exc:
            logger.warning("telegram notify failed for alert %s: %s", payload.alert_id, exc)
        finally:
            otel_context.detach(token)

    task = asyncio.create_task(runner())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


class AlertUseCase:
    LIST_PREFIX = "cache:alerts:list:"
    TTL = 30

    def __init__(self, repo: AlertRepository, redis: Redis) -> None:
        self._repo = repo
        self._redis = redis

    async def create(self, payload: AlertCreate) -> AlertResponse:
        doc = payload.model_dump()
        doc["created_at"] = datetime.now(timezone.utc)
        doc["acknowledged"] = False
        created = await self._repo.create(doc)
        _spawn_notify(payload)
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
