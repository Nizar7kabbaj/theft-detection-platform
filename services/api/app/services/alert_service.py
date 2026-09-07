from __future__ import annotations

import logging
from datetime import UTC

import grpc
from google.protobuf.timestamp_pb2 import Timestamp
from opentelemetry import trace

from app.core.errors import AlertRejectedError, AlertUnavailableError
from app.grpc_gen import alert_pb2 as pb
from app.grpc_gen import common_pb2
from app.grpc_gen.alert_pb2_grpc import AlertServiceStub
from app.schemas.alert import AlertCreate, Bbox, Keypoint, Object, Person
from app.schemas.delivery import DeliveryRecord, DeliveryState, DeliveryStatusView

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)
_TRANSIENT_CODES = {
    grpc.StatusCode.UNAVAILABLE,
    grpc.StatusCode.DEADLINE_EXCEEDED,
}
_RECIPIENT_TAIL = 4


def _to_bbox(bbox: Bbox | None) -> common_pb2.Bbox | None:
    if bbox is None:
        return None
    return common_pb2.Bbox(x1=bbox.x1, y1=bbox.y1, x2=bbox.x2, y2=bbox.y2)


def _to_keypoints(items: list[Keypoint]) -> list[common_pb2.Keypoint]:
    return [common_pb2.Keypoint(x=kp.x, y=kp.y, confidence=kp.confidence) for kp in items]


def _to_person(person: Person | None) -> common_pb2.Person | None:
    if person is None:
        return None
    msg = common_pb2.Person(
        track_id=person.track_id,
        keypoints=_to_keypoints(person.keypoints),
    )
    bbox = _to_bbox(person.bbox)
    if bbox is not None:
        msg.bbox.CopyFrom(bbox)
    return msg


def _to_object(obj: Object | None) -> common_pb2.Object | None:
    if obj is None:
        return None
    msg = common_pb2.Object(class_name=obj.class_name)
    bbox = _to_bbox(obj.bbox)
    if bbox is not None:
        msg.bbox.CopyFrom(bbox)
    return msg


def _to_proto(payload: AlertCreate) -> pb.Alert:
    occurred_at = Timestamp()
    occurred_at.FromDatetime(payload.occurred_at)
    msg = pb.Alert(
        alert_id=payload.alert_id,
        session_id=payload.session_id,
        frame_index=payload.frame_index,
        occurred_at=occurred_at,
        severity=common_pb2.Severity.Value(payload.severity.value),
        alert_type=common_pb2.AlertType.Value(payload.alert_type.value),
    )
    if payload.camera_id is not None:
        msg.camera_id = payload.camera_id
    person = _to_person(payload.person)
    if person is not None:
        msg.person.CopyFrom(person)
    obj = _to_object(payload.object)
    if obj is not None:
        msg.object.CopyFrom(obj)
    if payload.snapshot_path is not None:
        msg.snapshot_path = payload.snapshot_path
    if payload.clip_path is not None:
        msg.clip_path = payload.clip_path
    return msg


_DELIVERY_STATES = {
    pb.DELIVERY_STATE_PENDING: DeliveryState.PENDING,
    pb.DELIVERY_STATE_SENDING: DeliveryState.SENDING,
    pb.DELIVERY_STATE_SENT: DeliveryState.SENT,
    pb.DELIVERY_STATE_FAILED: DeliveryState.FAILED,
    pb.DELIVERY_STATE_DEAD: DeliveryState.DEAD,
    pb.DELIVERY_STATE_BUFFERED: DeliveryState.BUFFERED,
}


def _mask_recipient(value: str) -> str:
    trimmed = value.strip()
    if len(trimmed) <= _RECIPIENT_TAIL:
        return "****"
    return f"****{trimmed[-_RECIPIENT_TAIL:]}"


def _to_delivery_record(record: pb.DeliveryRecord) -> DeliveryRecord:
    return DeliveryRecord(
        channel=record.channel,
        recipient=_mask_recipient(record.recipient),
        state=_DELIVERY_STATES.get(record.state, DeliveryState.UNKNOWN),
        attempts=record.attempts,
        requeue_count=record.requeue_count,
        last_error_class=record.last_error_class or None,
        created_at=record.created_at.ToDatetime(tzinfo=UTC),
        updated_at=record.updated_at.ToDatetime(tzinfo=UTC),
    )


class AlertClient:
    def __init__(self, stub: AlertServiceStub) -> None:
        self._stub = stub

    async def send(self, payload: AlertCreate) -> None:
        proto = _to_proto(payload)
        with tracer.start_as_current_span("alert.send") as span:
            span.set_attribute("alert.id", payload.alert_id)
            span.set_attribute("alert.severity", payload.severity.value)
            span.set_attribute("alert.type", payload.alert_type.value)
            try:
                response = await self._stub.SendAlert(proto)
            except grpc.aio.AioRpcError as exc:
                if exc.code() in _TRANSIENT_CODES:
                    logger.warning(
                        "alert call failed code=%s detail=%s",
                        exc.code().name,
                        exc.details(),
                    )
                    raise AlertUnavailableError("alert service unavailable") from exc
                raise
            status_name = pb.Status.Name(response.status)
            span.set_attribute("alert.status", status_name)
            if response.status == pb.STATUS_RATE_LIMITED:
                logger.warning("alert %s rate limited by notification", payload.alert_id)
                raise AlertUnavailableError("alert service rate limited")
            if response.status != pb.STATUS_ACCEPTED:
                logger.error(
                    "alert %s refused by notification status=%s",
                    payload.alert_id,
                    status_name,
                )
                raise AlertRejectedError(f"alert refused: {status_name}")

    async def delivery_status(self, alert_id: str) -> DeliveryStatusView | None:
        with tracer.start_as_current_span("alert.delivery_status") as span:
            span.set_attribute("alert.id", alert_id)
            try:
                response = await self._stub.GetDeliveryStatus(
                    pb.DeliveryStatusRequest(alert_id=alert_id),
                    timeout=2.0,
                )
            except grpc.aio.AioRpcError as exc:
                logger.warning(
                    "delivery status unavailable for %s code=%s",
                    alert_id,
                    exc.code().name,
                )
                return None
            span.set_attribute("delivery.known", response.known)
            span.set_attribute("delivery.record_count", len(response.records))
            return DeliveryStatusView(
                known=response.known,
                records=[_to_delivery_record(record) for record in response.records],
            )

    async def delivery_status_batch(
        self,
        alert_ids: list[str],
    ) -> dict[str, DeliveryStatusView]:
        if not alert_ids:
            return {}
        with tracer.start_as_current_span("alert.delivery_status_batch") as span:
            span.set_attribute("delivery.requested", len(alert_ids))
            try:
                response = await self._stub.GetDeliveryStatusBatch(
                    pb.DeliveryStatusBatchRequest(alert_ids=alert_ids),
                    timeout=3.0,
                )
            except grpc.aio.AioRpcError as exc:
                logger.warning(
                    "batch delivery status unavailable count=%d code=%s",
                    len(alert_ids),
                    exc.code().name,
                )
                return {}
            span.set_attribute("delivery.entry_count", len(response.entries))
            return {
                entry.alert_id: DeliveryStatusView(
                    known=entry.known,
                    records=[_to_delivery_record(record) for record in entry.records],
                )
                for entry in response.entries
            }
