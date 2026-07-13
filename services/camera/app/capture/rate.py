from __future__ import annotations
import logging
import time
from collections.abc import Callable


logger = logging.getLogger(__name__)


class RateController:
    def __init__(
        self,
        set_pace: Callable[[int], None],
        idle_fps: int,
        active_fps: int,
        dwell_seconds: float,
    ) -> None:
        self._set_pace = set_pace
        self._idle_fps = idle_fps
        self._active_fps = active_fps
        self._dwell_seconds = dwell_seconds
        self._current_fps = idle_fps
        self._last_present_monotonic = 0.0
    @property
    def current_fps(self) -> int:
        return self._current_fps
    def observe(self, present: bool) -> None:
        now = time.monotonic()
        if present:
            self._last_present_monotonic = now
            desired = self._active_fps
        elif now - self._last_present_monotonic < self._dwell_seconds:
            desired = self._active_fps
        else:
            desired = self._idle_fps
        if desired != self._current_fps:
            self._current_fps = desired
            self._set_pace(desired)
            logger.info("rate changed fps=%d present=%s", desired, present)
