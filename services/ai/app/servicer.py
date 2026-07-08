from __future__ import annotations
import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
import grpc
from opentelemetry import trace
from app.grpc_gen import common_pb2, inference_pb2, inference_pb2_grpc
from app.inference import Detector, DetectionResult
from app.observability import get_frames_counter, get_inference_histogram
logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)
class InferenceServicer(inference_pb2_grpc.InferenceServiceServicer):
    def __init__(self, detector: Detector, executor: ThreadPoolExecutor) -> None:
        self._detector = detector
        self._executor = executor
        self._frames_counter = get_frames_counter()
        self._inference_histogram = get_inference_histogram()
    async def Analyze(
        self,
        request: inference_pb2.Frame,
        context: grpc.aio.ServicerContext,
    ) -> inference_pb2.Detection:
        result = await self._run_inference(request)
        if result is None:
            return inference_pb2.Detection(detection_present=False)
        return _to_proto(result)
    async def _run_inference(self, frame: inference_pb2.Frame) -> DetectionResult | None:
        with tracer.start_as_current_span("inference.analyze_frame") as span:
            span.set_attribute("session_id", frame.session_id)
            span.set_attribute("camera_id", frame.camera_id)
            span.set_attribute("frame_index", frame.frame_index)
            span.set_attribute("payload_bytes", len(frame.payload))
            loop = asyncio.get_running_loop()
            started = time.perf_counter()
            result = await loop.run_in_executor(
                self._executor,
                self._detector.analyze_frame,
                frame.payload,
                frame.session_id,
                frame.frame_index,
                frame.camera_id,
            )
            elapsed_ms = (time.perf_counter() - started) * 1000
            self._frames_counter.add(1, {"camera_id": frame.camera_id})
            self._inference_histogram.record(elapsed_ms, {"camera_id": frame.camera_id})
            if result is not None:
                span.set_attribute("inference_state", inference_pb2.InferenceState.Name(result.inference_state))
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
        inference_state=result.inference_state,
        track_id=result.track_id,
        detection_present=True,
    )
