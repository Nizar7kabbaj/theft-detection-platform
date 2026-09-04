from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from app.capture.buffer import CapturedFrame, ForwardBuffer
from app.capture.device import CameraDevice
from app.capture.publisher import FramePublisher

logger = logging.getLogger(__name__)


class CaptureLoop:
    def __init__(
        self,
        device: CameraDevice,
        buffer: ForwardBuffer,
        publisher: FramePublisher,
        camera_id: str,
        target_fps: int,
        heartbeat_path: Path,
    ) -> None:
        self._device = device
        self._buffer = buffer
        self._publisher = publisher
        self._camera_id = camera_id
        self._heartbeat_path = heartbeat_path
        self._frame_interval = 1.0 / target_fps
        self._thread: threading.Thread | None = None
        self._running = threading.Event()
        self._paused = threading.Event()
        self._frame_index = 0
        self._last_grab_monotonic = 0.0
        self._lock = threading.Lock()

    def start(self) -> None:
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
            record = self._build_record(frame)
            if record is not None:
                self._buffer.push(record)
                self._publisher.push(record)
            self._pace(started)

    def _build_record(self, frame) -> CapturedFrame | None:
        payload = frame.tobytes()
        if not payload:
            logger.warning("empty frame camera=%s", self._camera_id)
            return None
        now = time.monotonic()
        with self._lock:
            self._last_grab_monotonic = now
        self._touch_heartbeat()
        record = CapturedFrame(
            payload=payload,
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
            self._heartbeat_path.touch()
        except OSError:
            logger.warning("heartbeat write failed path=%s", self._heartbeat_path)

    def _pace(self, started: float) -> None:
        elapsed = time.monotonic() - started
        remaining = self._frame_interval - elapsed
        if remaining > 0:
            time.sleep(remaining)
