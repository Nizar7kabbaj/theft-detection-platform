from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import grpc
from google.protobuf.timestamp_pb2 import Timestamp
from opentelemetry import trace

from app.core.errors import InferenceUnavailable
from app.grpc_gen import inference_pb2 as pb
from app.grpc_gen.inference_pb2_grpc import InferenceServiceStub

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

_TRANSIENT_CODES = {
    grpc.StatusCode.UNAVAILABLE,
    grpc.StatusCode.DEADLINE_EXCEEDED,
}


@dataclass(frozen=True, slots=True)
class InferenceResult:
    bbox: dict[str, float]
    keypoints: list[dict[str, float]]
    score: float
    alert_type: str


class InferenceClient:
    def __init__(self, stub: InferenceServiceStub) -> None:
        self._stub = stub

    async def analyze(
        self,
        payload: bytes,
        session_id: int,
        frame_index: int,
    ) -> InferenceResult:
        ts = Timestamp()
        ts.FromDatetime(datetime.now(timezone.utc))
        frame = pb.Frame(
            payload=payload,
            session_id=session_id,
            frame_index=frame_index,
            timestamp=ts,
        )
        with tracer.start_as_current_span("inference.analyze") as span:
            span.set_attribute("frame.bytes", len(payload))
            span.set_attribute("session_id", session_id)
            span.set_attribute("frame_index", frame_index)
            try:
                response = await self._stub.Analyze(frame)
            except grpc.aio.AioRpcError as exc:
                if exc.code() in _TRANSIENT_CODES:
                    logger.warning(
                        "inference call failed code=%s detail=%s",
                        exc.code().name,
                        exc.details(),
                    )
                    raise InferenceUnavailable("inference service unavailable") from exc
                raise
            span.set_attribute("detection.score", response.score)
            span.set_attribute("detection.alert_type", response.alert_type)
            return _to_result(response)


def _to_result(response: pb.Detection) -> InferenceResult:
    bbox = response.bbox
    return InferenceResult(
        bbox={"x1": bbox.x1, "y1": bbox.y1, "x2": bbox.x2, "y2": bbox.y2},
        keypoints=[
            {"x": kp.x, "y": kp.y, "confidence": kp.confidence}
            for kp in response.keypoints
        ],
        score=response.score,
        alert_type=response.alert_type,
    )
