from __future__ import annotations

import threading
from collections import deque


class ClipBuffer:
    def __init__(self, max_frames: int) -> None:
        self._max_frames = max_frames
        self._lock = threading.Lock()
        self._frames: dict[str, deque[tuple[float, bytes]]] = {}

    def append(self, camera_id: str, captured_at: float, image_bytes: bytes) -> None:
        with self._lock:
            frames = self._frames.get(camera_id)
            if frames is None:
                frames = deque(maxlen=self._max_frames)
                self._frames[camera_id] = frames
            frames.append((captured_at, image_bytes))

    def snapshot(self, camera_id: str) -> list[tuple[float, bytes]]:
        with self._lock:
            frames = self._frames.get(camera_id)
            if frames is None:
                return []
            return list(frames)

    def clear(self, camera_id: str) -> None:
        with self._lock:
            self._frames.pop(camera_id, None)
