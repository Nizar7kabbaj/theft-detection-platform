from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import grpc
from google.protobuf.json_format import MessageToDict
from google.protobuf.timestamp_pb2 import Timestamp
from opentelemetry import trace
from pydantic import ValidationError

from app.core.database import get_collection
from app.repositories.delivery_intent import DeliveryIntentRepository
from app.server.grpc_gen import alert_pb2, alert_pb2_grpc
from app.shared.celery_app import celery_app
from app.shared.config import settings
from app.shared.observability import inject_context
from app.shared.recipient import resolve_recipient
from app.shared.schemas.alert import AlertMessage
from app.shared.schemas.delivery import (
    Channel,
    DeliveryIntent,
    DeliveryIntentCreate,
    DeliverySource,
    DeliveryStatus,
)

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("alert.servicer")

_BATCH_LIMIT = 200

_DELIVERY_STATES = {
    DeliveryStatus.PENDING: alert_pb2.DELIVERY_STATE_PENDING,
    DeliveryStatus.SENDING: alert_pb2.DELIVERY_STATE_SENDING,
    DeliveryStatus.SENT: alert_pb2.DELIVERY_STATE_SENT,
    DeliveryStatus.FAILED: alert_pb2.DELIVERY_STATE_FAILED,
    DeliveryStatus.DEAD: alert_pb2.DELIVERY_STATE_DEAD,
    DeliveryStatus.BUFFERED: alert_pb2.DELIVERY_STATE_BUFFERED,
}


def _error_class(last_error: str | None) -> str | None:
    if last_error is None:
        return None
    head = last_error.split(":", 1)[0].strip()
    return head or None


def _stamp(value: datetime) -> Timestamp:
    out = Timestamp()
    out.FromDatetime(value)
    return out


def _to_record(intent: DeliveryIntent) -> alert_pb2.DeliveryRecord:
    record = alert_pb2.DeliveryRecord(
        channel=intent.channel.value,
        recipient=intent.recipient,
        state=_DELIVERY_STATES.get(intent.status, alert_pb2.DELIVERY_STATE_UNSPECIFIED),
        attempts=intent.attempts,
        requeue_count=intent.requeue_count,
        created_at=_stamp(intent.created_at),
        updated_at=_stamp(intent.updated_at),
    )
    error_class = _error_class(intent.last_error)
    if error_class is not None:
        record.last_error_class = error_class
    return record


class AlertServicer(alert_pb2_grpc.AlertServiceServicer):
    async def SendAlert(
        self,
        request: alert_pb2.Alert,
        context: grpc.aio.ServicerContext,
    ) -> alert_pb2.SendAlertReply:
        alert_id = request.alert_id or "unknown"
        with tracer.start_as_current_span("alert.enqueue") as span:
            span.set_attribute("alert.id", alert_id)
            span.set_attribute("alert.severity", request.severity)

            raw = MessageToDict(
                request,
                preserving_proto_field_name=True,
                always_print_fields_with_no_presence=True,
            )
            try:
                payload = AlertMessage.model_validate(raw)
            except ValidationError as exc:
                logger.error(
                    "alert %s failed validation: %s",
                    alert_id,
                    exc.errors(include_url=False),
                )
                span.set_attribute("alert.validated", False)
                return alert_pb2.SendAlertReply(
                    status=alert_pb2.STATUS_FAILED,
                    delivered_at=Timestamp(),
                )
            span.set_attribute("alert.validated", True)

            try:
                intent_repo = DeliveryIntentRepository(
                    get_collection(settings.DELIVERY_INTENT_COLLECTION)
                )
                intent = await intent_repo.acquire(
                    DeliveryIntentCreate(
                        source=DeliverySource.ALERT,
                        source_ref=payload.alert_id,
                        channel=Channel.TELEGRAM,
                        recipient=resolve_recipient(),
                        payload=payload.model_dump(mode="json"),
                        trace_carrier=inject_context(),
                    )
                )
            except Exception as exc:
                logger.error("intent write failed for alert %s: %s", alert_id, exc)
                span.set_attribute("alert.persisted", False)
                return alert_pb2.SendAlertReply(
                    status=alert_pb2.STATUS_FAILED,
                    delivered_at=Timestamp(),
                )
            span.set_attribute("alert.persisted", True)
            span.set_attribute("intent.id", intent.id)

            try:
                await asyncio.to_thread(
                    celery_app.send_task,
                    "app.worker.tasks.send_alert_task",
                    args=[intent.id],
                )
            except Exception as exc:
                logger.warning(
                    "enqueue failed for alert %s intent=%s: %s, reconciler will pick up",
                    alert_id,
                    intent.id,
                    exc,
                )
                span.set_attribute("alert.enqueued", False)
            else:
                span.set_attribute("alert.enqueued", True)
                logger.info("alert %s enqueued intent=%s", alert_id, intent.id)

            now = Timestamp()
            now.GetCurrentTime()
            return alert_pb2.SendAlertReply(
                status=alert_pb2.STATUS_ACCEPTED,
                delivered_at=now,
            )

    async def GetDeliveryStatus(
        self,
        request: alert_pb2.DeliveryStatusRequest,
        context: grpc.aio.ServicerContext,
    ) -> alert_pb2.DeliveryStatusReply:
        alert_id = request.alert_id.strip()
        if not alert_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "alert_id required")
        with tracer.start_as_current_span("alert.delivery_status") as span:
            span.set_attribute("alert.id", alert_id)
            try:
                intent_repo = DeliveryIntentRepository(
                    get_collection(settings.DELIVERY_INTENT_COLLECTION)
                )
                intents = await intent_repo.list_by_source_ref(
                    DeliverySource.ALERT,
                    alert_id,
                )
            except Exception as exc:
                logger.error("delivery lookup failed for alert %s: %s", alert_id, exc)
                await context.abort(grpc.StatusCode.UNAVAILABLE, "delivery lookup failed")
            span.set_attribute("delivery.record_count", len(intents))
            return alert_pb2.DeliveryStatusReply(
                known=bool(intents),
                records=[_to_record(intent) for intent in intents],
            )

    async def GetDeliveryStatusBatch(
        self,
        request: alert_pb2.DeliveryStatusBatchRequest,
        context: grpc.aio.ServicerContext,
    ) -> alert_pb2.DeliveryStatusBatchReply:
        wanted = [value.strip() for value in request.alert_ids if value.strip()]
        if len(wanted) > _BATCH_LIMIT:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                f"at most {_BATCH_LIMIT} alert ids per request",
            )
        unique = list(dict.fromkeys(wanted))
        with tracer.start_as_current_span("alert.delivery_status_batch") as span:
            span.set_attribute("delivery.requested", len(unique))
            if not unique:
                return alert_pb2.DeliveryStatusBatchReply()
            try:
                intent_repo = DeliveryIntentRepository(
                    get_collection(settings.DELIVERY_INTENT_COLLECTION)
                )
                intents = await intent_repo.list_by_source_refs(
                    DeliverySource.ALERT,
                    unique,
                )
            except Exception as exc:
                logger.error("batch delivery lookup failed: %s", exc)
                await context.abort(grpc.StatusCode.UNAVAILABLE, "delivery lookup failed")
            grouped: dict[str, list[DeliveryIntent]] = {alert_id: [] for alert_id in unique}
            for intent in intents:
                grouped.setdefault(intent.source_ref, []).append(intent)
            span.set_attribute("delivery.record_count", len(intents))
            return alert_pb2.DeliveryStatusBatchReply(
                entries=[
                    alert_pb2.DeliveryStatusEntry(
                        alert_id=alert_id,
                        known=bool(rows),
                        records=[_to_record(intent) for intent in rows],
                    )
                    for alert_id, rows in grouped.items()
                ]
            )
