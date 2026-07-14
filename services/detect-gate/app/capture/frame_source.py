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
    def _open(self) -> None:
        capture = cv2.VideoCapture(self._clip_path)
        if not capture.isOpened():
            raise RuntimeError(f"cannot open clip {self._clip_path}")
        self._capture = capture
    def _grab(self) -> np.ndarray | None:
        if self._capture is None:
            self._open()
        assert self._capture is not None
        ok, frame = self._capture.read()
        if not ok:
            self._capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self._capture.read()
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
