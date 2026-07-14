from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol
import numpy as np
from ultralytics import YOLO


@dataclass(frozen=True, slots=True)
class GateResult:
    person_seen: bool
    top_confidence: float
class Detector(Protocol):
    def load(self) -> None: ...
    def detect(self, frame: np.ndarray) -> GateResult: ...
    def close(self) -> None: ...
class PersonDetector:
    def __init__(
        self,
        model_name: str,
        device: str,
        person_class: int,
        confidence: float,
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._person_class = person_class
        self._confidence = confidence
        self._yolo: YOLO | None = None
    @property
    def device(self) -> str:
        if self._yolo is None:
            return "unloaded"
        return str(self._yolo.device)
    def load(self) -> None:
        self._yolo = YOLO(self._model_name)
        self._yolo.to(self._device)
    def detect(self, frame: np.ndarray) -> GateResult:
        if self._yolo is None:
            raise RuntimeError("detector not loaded")
        results = self._yolo(
            frame,
            classes=[self._person_class],
            conf=self._confidence,
            verbose=False,
        )
        if not results:
            return GateResult(person_seen=False, top_confidence=0.0)
        boxes = results[0].boxes
        if boxes is None or len(boxes) == 0 or boxes.conf is None:
            return GateResult(person_seen=False, top_confidence=0.0)
        confs = boxes.conf.cpu().numpy()
        if confs.size == 0:
            return GateResult(person_seen=False, top_confidence=0.0)
        return GateResult(person_seen=True, top_confidence=float(confs.max()))
    def close(self) -> None:
        self._yolo = None
