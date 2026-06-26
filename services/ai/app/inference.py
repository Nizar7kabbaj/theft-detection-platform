from __future__ import annotations

import sys
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np

_AI_MODEL_SCRIPTS = Path("/app/ai-model/scripts")
if _AI_MODEL_SCRIPTS.exists() and str(_AI_MODEL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_AI_MODEL_SCRIPTS))

from predictor import ShoplifterPredictor
from ultralytics import YOLO


@dataclass(frozen=True, slots=True)
class DetectionResult:
    bbox: tuple[float, float, float, float]
    keypoints: list[tuple[float, float, float]]
    score: float
    alert_type: str
    track_id: int


class Detector(Protocol):
    def load(self) -> None: ...

    def analyze_frame(
        self,
        image_bytes: bytes,
        session_id: int,
        frame_index: int,
    ) -> DetectionResult | None: ...

    def reset_session(self, session_id: int) -> None: ...


class LSTMDetector:
    def __init__(
        self,
        yolo_model_name: str,
        lstm_model_path: str,
        device: str,
        anomaly_threshold: float,
        person_class: int,
    ) -> None:
        self._yolo_model_name = yolo_model_name
        self._lstm_model_path = lstm_model_path
        self._device = device
        self._anomaly_threshold = anomaly_threshold
        self._person_class = person_class
        self._yolo: YOLO | None = None
        self._predictor: ShoplifterPredictor | None = None

    def load(self) -> None:
        self._yolo = YOLO(self._yolo_model_name)
        self._yolo.to(self._device)
        self._predictor = ShoplifterPredictor(self._lstm_model_path, device=self._device)

    def analyze_frame(
        self,
        image_bytes: bytes,
        session_id: int,
        frame_index: int,
    ) -> DetectionResult | None:
        if self._yolo is None or self._predictor is None:
            raise RuntimeError("detector not loaded")

        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            return None

        results = self._yolo.track(
            frame,
            persist=True,
            classes=[self._person_class],
            verbose=False,
        )
        if not results:
            return None

        result = results[0]
        if result.boxes is None or result.keypoints is None or len(result.boxes) == 0:
            return None

        boxes = result.boxes
        kpts = result.keypoints

        confs = boxes.conf.cpu().numpy() if boxes.conf is not None else np.array([])
        if confs.size == 0:
            return None

        top = int(np.argmax(confs))

        coords = boxes.xyxy[top].cpu().numpy().astype(float)
        kp_xy = kpts.xy[top].cpu().numpy()
        kp_conf = kpts.conf[top].cpu().numpy() if kpts.conf is not None else np.zeros(kp_xy.shape[0])

        track_ids = boxes.id.cpu().numpy() if boxes.id is not None else None
        if track_ids is None or top >= len(track_ids):
            return None
        track_id = int(track_ids[top])

        kp_array = np.zeros((kp_xy.shape[0], 3), dtype=np.float32)
        kp_array[:, 0] = kp_xy[:, 0]
        kp_array[:, 1] = kp_xy[:, 1]
        kp_array[:, 2] = kp_conf

        _, p_anomaly = self._predictor.update(
            track_id=track_id,
            bbox_xyxy=tuple(coords),
            keypoints=kp_array,
        )

        if p_anomaly is None:
            alert_type = "warming_up"
            score = 0.0
        elif p_anomaly >= self._anomaly_threshold:
            alert_type = "anomaly"
            score = float(p_anomaly)
        else:
            alert_type = "normal"
            score = float(p_anomaly)

        keypoints_out = [
            (float(kp_array[i, 0]), float(kp_array[i, 1]), float(kp_array[i, 2]))
            for i in range(kp_array.shape[0])
        ]

        return DetectionResult(
            bbox=(float(coords[0]), float(coords[1]), float(coords[2]), float(coords[3])),
            keypoints=keypoints_out,
            score=score,
            alert_type=alert_type,
            track_id=track_id,
        )

    def reset_session(self, session_id: int) -> None:
        if self._predictor is None:
            return
        for tid in self._predictor.active_track_ids():
            self._predictor.drop_track(tid)
