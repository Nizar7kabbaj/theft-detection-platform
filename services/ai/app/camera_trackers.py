from __future__ import annotations

from collections.abc import Callable
from typing import Any


class CameraTrackers:
    def __init__(self, fresh: Callable[..., None]) -> None:
        self._fresh = fresh
        self._by_camera: dict[str, list[Any]] = {}

    def track(self, model: Any, camera_id: str, frame: Any, **kwargs: Any) -> list[Any]:
        predictor = model.predictor
        if predictor is not None and hasattr(predictor, "trackers"):
            saved = self._by_camera.get(camera_id)
            if saved is None:
                self._fresh(predictor, persist=False)
                saved = predictor.trackers
            predictor.trackers = saved
        results = model.track(frame, persist=True, **kwargs)
        self._by_camera[camera_id] = model.predictor.trackers
        return results

    def cameras(self) -> list[str]:
        return sorted(self._by_camera)
