from __future__ import annotations

import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np

from app.concealment import ConcealmentTracker, ConcealmentVerdict
from app.core.config import settings
from app.tracker_store import TrackerStore

_AI_MODEL_SCRIPTS = Path("/app/ai-model/scripts")
if _AI_MODEL_SCRIPTS.exists() and str(_AI_MODEL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_AI_MODEL_SCRIPTS))

from predictor import ShoplifterPredictor
from ultralytics import YOLO

from app.grpc_gen.inference_pb2 import InferenceState


@dataclass(frozen=True, slots=True)
class TrackedPersonResult:
    track_id: int
    bbox: tuple[float, float, float, float]
    keypoints: list[tuple[float, float, float]]
    score: float
    inference_state: InferenceState.ValueType


@dataclass(frozen=True, slots=True)
class TrackedObjectResult:
    track_id: int
    class_name: str
    bbox: tuple[float, float, float, float]
    confidence: float


@dataclass(frozen=True, slots=True)
class DetectionResult:
    bbox: tuple[float, float, float, float]
    keypoints: list[tuple[float, float, float]]
    score: float
    inference_state: InferenceState.ValueType
    track_id: int
    persons: list[TrackedPersonResult]
    objects: list[TrackedObjectResult]
    concealments: list[ConcealmentVerdict]
    snapshots: dict[int, str]
    frame_width: int
    frame_height: int


class Detector(Protocol):
    def load(self) -> None: ...
    def analyze_frame(
        self,
        image_bytes: bytes,
        session_id: int,
        frame_index: int,
        camera_id: str,
        run_pose: bool,
        captured_at: float,
    ) -> DetectionResult | None: ...
    def close(self) -> None: ...


class LSTMDetector:
    def __init__(
        self,
        yolo_model_name: str,
        object_model_name: str,
        lstm_model_path: str,
        device: str,
        anomaly_threshold: float,
        person_class: int,
        person_confidence: float,
        object_classes: list[int],
        object_confidence: float,
        grab_ratio: float,
        missing_seconds: float,
        keypoint_confidence: float,
        expiry_seconds: float,
        snapshot_dir: str,
    ) -> None:
        self._yolo_model_name = yolo_model_name
        self._object_model_name = object_model_name
        self._lstm_model_path = lstm_model_path
        self._device = device
        self._anomaly_threshold = anomaly_threshold
        self._person_class = person_class
        self._person_confidence = person_confidence
        self._object_classes = object_classes
        self._object_confidence = object_confidence
        self._snapshot_dir = Path(snapshot_dir)
        self._concealment = ConcealmentTracker(
            grab_ratio=grab_ratio,
            missing_seconds=missing_seconds,
            keypoint_confidence=keypoint_confidence,
            expiry_seconds=expiry_seconds,
        )
        self._yolo: YOLO | None = None
        self._objects: YOLO | None = None
        self._predictor: ShoplifterPredictor | None = None
        self._store: TrackerStore | None = None
        self._analyze_lock = threading.Lock()

    def load(self) -> None:
        self._store = TrackerStore(
            redis_url=settings.REDIS_URL,
            connection_kwargs=settings.redis_tls_options,
            window=30,
            ttl_seconds=settings.TRACKER_TTL_SECONDS,
        )
        self._yolo = YOLO(self._yolo_model_name)
        self._yolo.to(self._device)
        self._objects = YOLO(self._object_model_name)
        self._objects.to(self._device)
        self._predictor = ShoplifterPredictor(
            self._lstm_model_path,
            device=self._device,
            store=self._store,
        )

    def write_snapshot(self, frame: np.ndarray, alert_id: str) -> str | None:
        self._snapshot_dir.mkdir(parents=True, exist_ok=True)
        path = self._snapshot_dir / f"{alert_id}.jpg"
        if not cv2.imwrite(str(path), frame):
            return None
        return str(path)

    def analyze_frame(
        self,
        image_bytes: bytes,
        session_id: int,
        frame_index: int,
        camera_id: str,
        run_pose: bool = True,
        captured_at: float = 0.0,
    ) -> DetectionResult | None:
        with self._analyze_lock:
            if self._yolo is None or self._objects is None or self._predictor is None:
                raise RuntimeError("detector not loaded")
            arr = np.frombuffer(image_bytes, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is None:
                return None
            height, width = frame.shape[:2]
            persons = self._track_persons(frame, camera_id, frame_index) if run_pose else []
            objects = self._track_objects(frame)
            concealments = self._concealment.observe(
                camera_id=camera_id,
                frame_index=frame_index,
                captured_at=captured_at,
                persons=[(person.track_id, person.keypoints) for person in persons],
                objects=[(obj.track_id, obj.class_name, obj.bbox) for obj in objects],
            )
            snapshots: dict[int, str] = {}
            for verdict in concealments:
                alert_id = f"{camera_id}-{session_id}-{frame_index}-{verdict.object_track_id}"
                written = self.write_snapshot(frame, alert_id)
                if written is not None:
                    snapshots[verdict.object_track_id] = written
            if not persons and not objects and not concealments:
                return None
            lead = persons[0] if persons else None
            return DetectionResult(
                bbox=lead.bbox if lead else (0.0, 0.0, 0.0, 0.0),
                keypoints=lead.keypoints if lead else [],
                score=lead.score if lead else 0.0,
                inference_state=(
                    lead.inference_state if lead else InferenceState.INFERENCE_STATE_UNSPECIFIED
                ),
                track_id=lead.track_id if lead else 0,
                persons=persons,
                objects=objects,
                concealments=concealments,
                snapshots=snapshots,
                frame_width=width,
                frame_height=height,
            )

    def _track_persons(
        self,
        frame: np.ndarray,
        camera_id: str,
        frame_index: int,
    ) -> list[TrackedPersonResult]:
        if self._yolo is None or self._predictor is None:
            raise RuntimeError("models not loaded")
        results = self._yolo.track(
            frame,
            persist=True,
            classes=[self._person_class],
            conf=self._person_confidence,
            verbose=False,
        )
        if not results:
            return []
        result = results[0]
        if result.boxes is None or result.keypoints is None or len(result.boxes) == 0:
            return []
        boxes = result.boxes
        if boxes.id is None:
            return []
        kpts = result.keypoints
        xyxy = boxes.xyxy.cpu().numpy()
        track_ids = boxes.id.int().cpu().numpy()
        kp_xy = kpts.xy.cpu().numpy()
        kp_conf = kpts.conf.cpu().numpy() if kpts.conf is not None else None
        out: list[TrackedPersonResult] = []
        for index in range(len(xyxy)):
            coords = xyxy[index].astype(float)
            kp_array = np.zeros((kp_xy.shape[1], 3), dtype=np.float32)
            kp_array[:, 0] = kp_xy[index][:, 0]
            kp_array[:, 1] = kp_xy[index][:, 1]
            if kp_conf is not None:
                kp_array[:, 2] = kp_conf[index]
            track_id = int(track_ids[index])
            _, p_anomaly = self._predictor.update(
                camera_id=camera_id,
                track_id=track_id,
                bbox_xyxy=tuple(coords),
                keypoints=kp_array,
                frame_index=frame_index,
            )
            if p_anomaly is None:
                state = InferenceState.INFERENCE_STATE_WARMING_UP
                score = 0.0
            elif p_anomaly >= self._anomaly_threshold:
                state = InferenceState.INFERENCE_STATE_ANOMALY
                score = float(p_anomaly)
            else:
                state = InferenceState.INFERENCE_STATE_NORMAL
                score = float(p_anomaly)
            out.append(
                TrackedPersonResult(
                    track_id=track_id,
                    bbox=(
                        float(coords[0]),
                        float(coords[1]),
                        float(coords[2]),
                        float(coords[3]),
                    ),
                    keypoints=[
                        (
                            float(kp_array[i, 0]),
                            float(kp_array[i, 1]),
                            float(kp_array[i, 2]),
                        )
                        for i in range(kp_array.shape[0])
                    ],
                    score=score,
                    inference_state=state,
                )
            )
        out.sort(key=lambda person: person.score, reverse=True)
        return out

    def _track_objects(self, frame: np.ndarray) -> list[TrackedObjectResult]:
        if self._objects is None:
            raise RuntimeError("models not loaded")
        results = self._objects.track(
            frame,
            persist=True,
            classes=self._object_classes,
            conf=self._object_confidence,
            verbose=False,
        )
        if not results:
            return []
        result = results[0]
        if result.boxes is None or len(result.boxes) == 0 or result.boxes.id is None:
            return []
        boxes = result.boxes
        xyxy = boxes.xyxy.cpu().numpy()
        track_ids = boxes.id.int().cpu().numpy()
        confs = boxes.conf.cpu().numpy() if boxes.conf is not None else None
        class_ids = boxes.cls.int().cpu().numpy() if boxes.cls is not None else None
        names = result.names
        out: list[TrackedObjectResult] = []
        for index in range(len(xyxy)):
            coords = xyxy[index].astype(float)
            class_id = int(class_ids[index]) if class_ids is not None else -1
            out.append(
                TrackedObjectResult(
                    track_id=int(track_ids[index]),
                    class_name=str(names.get(class_id, "unknown")),
                    bbox=(
                        float(coords[0]),
                        float(coords[1]),
                        float(coords[2]),
                        float(coords[3]),
                    ),
                    confidence=float(confs[index]) if confs is not None else 0.0,
                )
            )
        return out

    def close(self) -> None:
        if self._store is not None:
            self._store.close()
            self._store = None
