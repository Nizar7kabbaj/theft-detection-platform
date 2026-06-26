from __future__ import annotations

import logging

import grpc
from google.protobuf.struct_pb2 import Struct
from opentelemetry import trace

from app.core.errors import AlertUnavailable
from app.grpc_gen import alert_pb2 as pb
from app.grpc_gen import common_pb2
from app.grpc_gen.alert_pb2_grpc import AlertServiceStub
from app.schemas.alert import AlertCreate

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

_TRANSIENT_CODES = {
    grpc.StatusCode.UNAVAILABLE,
    grpc.StatusCode.DEADLINE_EXCEEDED,
}


def _to_struct(data: dict | None) -> Struct | None:
    if not data:
        return None
    s = Struct()
    s.update(data)
    return s


def _to_keypoints(items: list[dict] | None) -> list[common_pb2.Keypoint]:
    if not items:
        return []
    return [
        common_pb2.Keypoint(
            x=float(kp.get("x", 0.0)),
            y=float(kp.get("y", 0.0)),
            confidence=float(kp.get("confidence", 0.0)),
        )
        for kp in items
    ]


def _to_proto(payload: AlertCreate) -> pb.Alert:
    msg = pb.Alert(
        alert_id=payload.alert_id,
        session_id=payload.session_id,
        frame_index=payload.frame_index,
        timestamp=payload.timestamp,
        severity=payload.severity,
        keypoints=_to_keypoints(payload.keypoints),
    )
    if payload.camera_id is not None:
        msg.camera_id = payload.camera_id
    person_struct = _to_struct(payload.person)
    if person_struct is not None:
        msg.person.CopyFrom(person_struct)
    object_struct = _to_struct(payload.object)
    if object_struct is not None:
        msg.object.CopyFrom(object_struct)
    if payload.snapshot_path is not None:
        msg.snapshot_path = payload.snapshot_path
    if payload.alert_type is not None:
        msg.alert_type = payload.alert_type
    if payload.torso_angle is not None:
        msg.torso_angle = payload.torso_angle
    return msg


class AlertClient:
    def __init__(self, stub: AlertServiceStub) -> None:
        self._stub = stub

    async def send(self, payload: AlertCreate) -> None:
        proto = _to_proto(payload)
        with tracer.start_as_current_span("alert.send") as span:
            span.set_attribute("alert.id", payload.alert_id)
            span.set_attribute("alert.severity", payload.severity)
            try:
                response = await self._stub.SendAlert(proto)
            except grpc.aio.AioRpcError as exc:
                if exc.code() in _TRANSIENT_CODES:
                    logger.warning(
                        "alert call failed code=%s detail=%s",
                        exc.code().name,
                        exc.details(),
                    )
                    raise AlertUnavailable("alert service unavailable") from exc
                raise
            span.set_attribute("alert.status", response.status)
