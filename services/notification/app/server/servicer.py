from __future__ import annotations

import asyncio
import logging

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
    DeliveryIntentCreate,
    DeliverySource,
)

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("alert.servicer")


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
                always_print_fields_with_no_presence=False,
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
