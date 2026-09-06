from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CapturedFrame:
    payload: bytes
    session_id: int
    frame_index: int
    camera_id: str
    timestamp_unix: float
    captured_at_monotonic: float


class ForwardBuffer:
    def __init__(self, max_depth: int, max_age_seconds: float) -> None:
        self._max_age_seconds = max_age_seconds
        self._frames: deque[CapturedFrame] = deque(maxlen=max_depth)
        self._lock = threading.Lock()
        self._captured_total = 0
        self._dropped_overflow_total = 0
        self._dropped_stale_total = 0

    def push(self, frame: CapturedFrame) -> None:
        with self._lock:
            if len(self._frames) == self._frames.maxlen:
                self._dropped_overflow_total += 1
            self._frames.append(frame)
            self._captured_total += 1

    def pop_fresh(self) -> CapturedFrame | None:
        now = time.monotonic()
        with self._lock:
            while self._frames:
                frame = self._frames.pop()
                self._dropped_stale_total += len(self._frames)
                self._frames.clear()
                if now - frame.captured_at_monotonic <= self._max_age_seconds:
                    return frame
                self._dropped_stale_total += 1
            return None

    @property
    def depth(self) -> int:
        with self._lock:
            return len(self._frames)

    @property
    def counters(self) -> dict[str, int]:
        with self._lock:
            return {
                "captured_total": self._captured_total,
                "dropped_overflow_total": self._dropped_overflow_total,
                "dropped_stale_total": self._dropped_stale_total,
                "depth": len(self._frames),
            }
