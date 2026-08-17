from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import grpc
from opentelemetry import trace

from app.alert_client import AlertClient
from app.grpc_gen import alert_pb2, common_pb2, inference_pb2, inference_pb2_grpc
from app.inference import DetectionResult, Detector
from app.observability import get_frames_counter, get_inference_histogram

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

_ANOMALY_SEVERITY = "SEVERITY_CRITICAL"
_DEFAULT_SEVERITY = "SEVERITY_WARNING"


class InferenceServicer(inference_pb2_grpc.InferenceServiceServicer):
    def __init__(
        self,
        detector: Detector,
        executor: ThreadPoolExecutor,
        alert_client: AlertClient | None = None,
    ) -> None:
        self._detector = detector
        self._executor = executor
        self._alert_client = alert_client
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
        if result.concealments and self._alert_client is not None:
            await self._emit_alerts(request, result)
        return _to_proto(result)

    async def _emit_alerts(
        self,
        frame: inference_pb2.Frame,
        result: DetectionResult,
    ) -> None:
        loop = asyncio.get_running_loop()
        persons = {person.track_id: person for person in result.persons}
        for verdict in result.concealments:
            person = persons.get(verdict.person_track_id)
            alert_id = (
                f"{frame.camera_id}-{frame.session_id}-"
                f"{frame.frame_index}-{verdict.object_track_id}"
            )
            severity = _DEFAULT_SEVERITY
            classifier_state = None
            classifier_score = None
            if person is not None:
                classifier_score = person.score
                classifier_state = inference_pb2.InferenceState.Name(person.inference_state)
                if person.inference_state == inference_pb2.INFERENCE_STATE_ANOMALY:
                    severity = _ANOMALY_SEVERITY
            payload: dict[str, object] = {
                "alert_id": alert_id,
                "session_id": frame.session_id,
                "frame_index": frame.frame_index,
                "occurred_at": datetime.now(UTC).isoformat(),
                "camera_id": frame.camera_id,
                "severity": severity,
                "alert_type": "ALERT_TYPE_CONCEALMENT",
                "frame_width": result.frame_width,
                "frame_height": result.frame_height,
                "object": {
                    "class_name": verdict.object_class,
                    "bbox": {
                        "x1": verdict.last_seen_bbox[0],
                        "y1": verdict.last_seen_bbox[1],
                        "x2": verdict.last_seen_bbox[2],
                        "y2": verdict.last_seen_bbox[3],
                    },
                },
                "concealment": {
                    "object_track_id": verdict.object_track_id,
                    "object_class": verdict.object_class,
                    "last_seen_frame": verdict.last_seen_frame,
                    "missing_frames": verdict.missing_frames,
                    "person_track_id": verdict.person_track_id,
                    "wrist_index": verdict.wrist_index,
                    "wrist_x": verdict.wrist_x,
                    "wrist_y": verdict.wrist_y,
                    "grab_distance": verdict.grab_distance,
                },
            }
            if person is not None:
                payload["person"] = {
                    "track_id": person.track_id,
                    "bbox": {
                        "x1": person.bbox[0],
                        "y1": person.bbox[1],
                        "x2": person.bbox[2],
                        "y2": person.bbox[3],
                    },
                    "keypoints": [
                        {"x": kp[0], "y": kp[1], "confidence": kp[2]} for kp in person.keypoints
                    ],
                }
            if classifier_score is not None:
                payload["classifier_score"] = classifier_score
            if classifier_state is not None:
                payload["classifier_state"] = classifier_state
            snapshot = result.snapshots.get(verdict.object_track_id)
            if snapshot is not None:
                payload["snapshot_path"] = snapshot
            sent = await loop.run_in_executor(
                self._executor,
                self._alert_client.send,
                payload,
            )
            if sent:
                logger.info(
                    "concealment alert sent id=%s object=%s",
                    alert_id,
                    verdict.object_class,
                )
            else:
                logger.warning("concealment alert not accepted id=%s", alert_id)

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
                span.set_attribute(
                    "inference_state", inference_pb2.InferenceState.Name(result.inference_state)
                )
                span.set_attribute("score", result.score)
                span.set_attribute("track_id", result.track_id)
                span.set_attribute("person_count", len(result.persons))
                span.set_attribute("object_count", len(result.objects))
                span.set_attribute("concealment_count", len(result.concealments))
            return result


def _bbox(values: tuple[float, float, float, float]) -> common_pb2.Bbox:
    return common_pb2.Bbox(x1=values[0], y1=values[1], x2=values[2], y2=values[3])


def _to_proto(result: DetectionResult) -> inference_pb2.Detection:
    return inference_pb2.Detection(
        bbox=_bbox(result.bbox),
        keypoints=[
            common_pb2.Keypoint(x=kp[0], y=kp[1], confidence=kp[2]) for kp in result.keypoints
        ],
        score=result.score,
        inference_state=result.inference_state,
        track_id=result.track_id,
        detection_present=True,
        persons=[
            inference_pb2.TrackedPerson(
                track_id=person.track_id,
                bbox=_bbox(person.bbox),
                keypoints=[
                    common_pb2.Keypoint(x=kp[0], y=kp[1], confidence=kp[2])
                    for kp in person.keypoints
                ],
                score=person.score,
                inference_state=person.inference_state,
            )
            for person in result.persons
        ],
        objects=[
            common_pb2.TrackedObject(
                track_id=obj.track_id,
                class_name=obj.class_name,
                bbox=_bbox(obj.bbox),
                confidence=obj.confidence,
            )
            for obj in result.objects
        ],
        concealments=[
            alert_pb2.Concealment(
                object_track_id=verdict.object_track_id,
                object_class=verdict.object_class,
                last_seen_bbox=_bbox(verdict.last_seen_bbox),
                last_seen_frame=verdict.last_seen_frame,
                missing_frames=verdict.missing_frames,
                person_track_id=verdict.person_track_id,
                wrist_index=verdict.wrist_index,
                wrist_x=verdict.wrist_x,
                wrist_y=verdict.wrist_y,
                grab_distance=verdict.grab_distance,
            )
            for verdict in result.concealments
        ],
        frame_width=result.frame_width,
        frame_height=result.frame_height,
    )
