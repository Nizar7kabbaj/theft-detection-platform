from __future__ import annotations

import asyncio
from typing import Protocol

import cv2
import numpy as np


class FrameSource(Protocol):
    async def read(self) -> np.ndarray | None: ...
    async def close(self) -> None: ...


class ClipFrameSource:
    def __init__(self, clip_path: str, target_fps: int) -> None:
        self._clip_path = clip_path
        self._frame_interval = 1.0 / target_fps
        self._capture: cv2.VideoCapture | None = None

    def _open(self) -> cv2.VideoCapture:
        capture = cv2.VideoCapture(self._clip_path)
        if not capture.isOpened():
            raise RuntimeError(f"cannot open clip {self._clip_path}")
        self._capture = capture
        return capture

    def _grab(self) -> np.ndarray | None:
        capture = self._capture or self._open()
        ok, frame = capture.read()
        if not ok:
            capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = capture.read()
            if not ok:
                return None
        return frame

    async def read(self) -> np.ndarray | None:
        loop = asyncio.get_running_loop()
        frame = await loop.run_in_executor(None, self._grab)
        await asyncio.sleep(self._frame_interval)
        return frame

    async def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None
