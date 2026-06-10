from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import AsyncIterator

import grpc
from opentelemetry import trace

from app.grpc_gen import common_pb2, inference_pb2, inference_pb2_grpc
from app.inference import Detector, DetectionResult

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class InferenceServicer(inference_pb2_grpc.InferenceServiceServicer):
    def __init__(self, detector: Detector, executor: ThreadPoolExecutor) -> None:
        self._detector = detector
        self._executor = executor

    async def Analyze(
        self,
        request: inference_pb2.Frame,
        context: grpc.aio.ServicerContext,
    ) -> inference_pb2.Detection:
        result = await self._run_inference(request)
        if result is None:
            return inference_pb2.Detection()
        return _to_proto(result)

    async def AnalyzeStream(
        self,
        request_iterator: AsyncIterator[inference_pb2.Frame],
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[inference_pb2.Detection]:
        async for frame in request_iterator:
            result = await self._run_inference(frame)
            if result is None:
                yield inference_pb2.Detection()
                continue
            yield _to_proto(result)

    async def _run_inference(self, frame: inference_pb2.Frame) -> DetectionResult | None:
        with tracer.start_as_current_span("inference.analyze_frame") as span:
            span.set_attribute("session_id", frame.session_id)
            span.set_attribute("frame_index", frame.frame_index)
            span.set_attribute("payload_bytes", len(frame.payload))

            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                self._executor,
                self._detector.analyze_frame,
                frame.payload,
                frame.session_id,
                frame.frame_index,
            )

            if result is not None:
                span.set_attribute("alert_type", result.alert_type)
                span.set_attribute("score", result.score)
                span.set_attribute("track_id", result.track_id)
            return result


def _to_proto(result: DetectionResult) -> inference_pb2.Detection:
    return inference_pb2.Detection(
        bbox=common_pb2.Bbox(
            x1=result.bbox[0],
            y1=result.bbox[1],
            x2=result.bbox[2],
            y2=result.bbox[3],
        ),
        keypoints=[
            common_pb2.Keypoint(x=kp[0], y=kp[1], confidence=kp[2])
            for kp in result.keypoints
        ],
        score=result.score,
        alert_type=result.alert_type,
    )
