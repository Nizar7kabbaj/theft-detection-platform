from __future__ import annotations

import os
import logging
import threading
import time

import cv2

from app.capture.buffer import CapturedFrame, ForwardBuffer
from app.capture.device import CameraDevice

logger = logging.getLogger(__name__)


class CaptureLoop:
    def __init__(
        self,
        device: CameraDevice,
        buffer: ForwardBuffer,
        camera_id: str,
        target_fps: int,
        jpeg_quality: int,
        heartbeat_path: str,
    ) -> None:
        self._device = device
        self._buffer = buffer
        self._camera_id = camera_id
        self._heartbeat_path = heartbeat_path
        self._frame_interval = 1.0 / target_fps
        self._encode_params = [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality]
        self._thread: threading.Thread | None = None
        self._running = threading.Event()
        self._paused = threading.Event()
        self._frame_index = 0
        self._last_grab_monotonic = 0.0
        self._lock = threading.Lock()

    def start(self) -> None:
        self._touch_heartbeat()
        if not self._device.open():
            self._device.reopen_with_backoff()
        self._running.set()
        self._thread = threading.Thread(target=self._run, name="capture", daemon=True)
        self._thread.start()
        logger.info("capture loop started camera=%s", self._camera_id)

    def stop(self) -> None:
        self._running.clear()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        self._device.close()
        logger.info("capture loop stopped camera=%s", self._camera_id)

    def pause(self) -> None:
        self._paused.set()

    def resume(self) -> None:
        self._paused.clear()

    def set_pace(self, target_fps: int) -> None:
        self._frame_interval = 1.0 / target_fps

    @property
    def last_grab_monotonic(self) -> float:
        with self._lock:
            return self._last_grab_monotonic

    def _run(self) -> None:
        while self._running.is_set():
            started = time.monotonic()
            if self._paused.is_set():
                time.sleep(self._frame_interval)
                continue
            frame = self._device.read()
            if frame is None:
                logger.warning("grab failed camera=%s, reopening", self._camera_id)
                self._device.reopen_with_backoff()
                self._frame_index = 0
                continue
            record = self._encode(frame)
            if record is not None:
                self._buffer.push(record)
            self._pace(started)

    def _encode(self, frame) -> CapturedFrame | None:
        ok, encoded = cv2.imencode(".jpg", frame, self._encode_params)
        if not ok:
            logger.warning("encode failed camera=%s", self._camera_id)
            return None
        now = time.monotonic()
        with self._lock:
            self._last_grab_monotonic = now
        self._touch_heartbeat()
        record = CapturedFrame(
            payload=encoded.tobytes(),
            session_id=self._device.session_id,
            frame_index=self._frame_index,
            camera_id=self._camera_id,
            timestamp_unix=time.time(),
            captured_at_monotonic=now,
        )
        self._frame_index += 1
        return record
    def _touch_heartbeat(self) -> None:
        try:
            with open(self._heartbeat_path, "a"):
                os.utime(self._heartbeat_path, None)
        except OSError:
            logger.warning("heartbeat write failed path=%s", self._heartbeat_path)
    def _pace(self, started: float) -> None:
        elapsed = time.monotonic() - started
        remaining = self._frame_interval - elapsed
        if remaining > 0:
            time.sleep(remaining)
