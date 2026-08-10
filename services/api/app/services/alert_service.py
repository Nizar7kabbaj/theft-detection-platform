from __future__ import annotations

import logging

import grpc
from google.protobuf.timestamp_pb2 import Timestamp
from opentelemetry import trace

from app.core.errors import AlertUnavailableError
from app.grpc_gen import alert_pb2 as pb
from app.grpc_gen import common_pb2
from app.grpc_gen.alert_pb2_grpc import AlertServiceStub
from app.schemas.alert import AlertCreate, Bbox, Keypoint, Object, Person

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)
_TRANSIENT_CODES = {
    grpc.StatusCode.UNAVAILABLE,
    grpc.StatusCode.DEADLINE_EXCEEDED,
}


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
    return msg


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
            span.set_attribute("alert.status", pb.Status.Name(response.status))
