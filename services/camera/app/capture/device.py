from __future__ import annotations
import logging
import time
import cv2
from numpy import ndarray


logger = logging.getLogger(__name__)

class CameraDevice:
    def __init__(
        self,
        device_path: str,
        frame_width: int,
        frame_height: int,
        target_fps: int,
        reopen_backoff_seconds: float,
        reopen_backoff_max_seconds: float,
    ) -> None:
        self._device_path = device_path
        self._frame_width = frame_width
        self._frame_height = frame_height
        self._target_fps = target_fps
        self._reopen_backoff = reopen_backoff_seconds
        self._reopen_backoff_max = reopen_backoff_max_seconds
        self._capture: cv2.VideoCapture | None = None
        self._session_id = 0
        self._actual_width = 0
        self._actual_height = 0
        self._actual_fps = 0.0
    @property
    def session_id(self) -> int:
        return self._session_id
    @property
    def actual_resolution(self) -> tuple[int, int]:
        return self._actual_width, self._actual_height
    @property
    def actual_fps(self) -> float:
        return self._actual_fps
    @property
    def is_open(self) -> bool:
        return self._capture is not None and self._capture.isOpened()
    def open(self) -> bool:
        self._release_handle()
        capture = cv2.VideoCapture(self._device_path, cv2.CAP_V4L2)
        if not capture.isOpened():
            logger.warning("device open failed: %s", self._device_path)
            capture.release()
            return False
        fourcc = cv2.VideoWriter_fourcc(*"MJPG")
        capture.set(cv2.CAP_PROP_FOURCC, fourcc)
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self._frame_width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self._frame_height)
        capture.set(cv2.CAP_PROP_FPS, self._target_fps)
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self._actual_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        self._actual_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self._actual_fps = capture.get(cv2.CAP_PROP_FPS)
        self._capture = capture
        self._session_id += 1
        logger.info(
            "device open: %s session=%d resolution=%dx%d fps=%.1f",
            self._device_path,
            self._session_id,
            self._actual_width,
            self._actual_height,
            self._actual_fps,
        )
        if self._actual_fps < self._target_fps:
            logger.warning(
                "negotiated fps below target: got %.1f asked %d",
                self._actual_fps,
                self._target_fps,
            )
        return True
    def read(self) -> ndarray | None:
        if self._capture is None:
            return None
        ok, frame = self._capture.read()
        if not ok or frame is None:
            return None
        return frame
    def reopen_with_backoff(self, on_retry=None) -> None:
        delay = self._reopen_backoff
        while True:
            if on_retry is not None:
                on_retry()
            logger.warning("device reopen in %.1fs", delay)
            time.sleep(delay)
            if self.open():
                return
            delay = min(delay * 2, self._reopen_backoff_max)
    def _release_handle(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None
    def close(self) -> None:
        self._release_handle()
        logger.info("device closed: %s", self._device_path)
