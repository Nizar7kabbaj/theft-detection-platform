from __future__ import annotations

import asyncio
import logging
from typing import Any

import grpc
from google.protobuf.json_format import MessageToDict
from google.protobuf.timestamp_pb2 import Timestamp
from opentelemetry import trace

from app.celery_app import celery_app
from app.grpc_gen import alert_pb2, alert_pb2_grpc

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("alert.servicer")


def _alert_to_dict(alert: alert_pb2.Alert) -> dict[str, Any]:
    data = MessageToDict(
        alert,
        preserving_proto_field_name=True,
        always_print_fields_with_no_presence=False,
    )
    if "session_id" in data and isinstance(data["session_id"], str):
        data["session_id"] = int(data["session_id"])
    return data


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

            payload = _alert_to_dict(request)

            try:
                await asyncio.to_thread(
                    celery_app.send_task,
                    "app.tasks.send_alert_task",
                    args=[payload],
                )
            except Exception as exc:
                logger.error("enqueue failed for alert %s: %s", alert_id, exc)
                span.set_attribute("alert.enqueued", False)
                return alert_pb2.SendAlertReply(
                    status=alert_pb2.STATUS_FAILED,
                    delivered_at=Timestamp(),
                )

            span.set_attribute("alert.enqueued", True)
            logger.info("alert %s enqueued", alert_id)

            now = Timestamp()
            now.GetCurrentTime()
            return alert_pb2.SendAlertReply(
                status=alert_pb2.STATUS_ACCEPTED,
                delivered_at=now,
            )
