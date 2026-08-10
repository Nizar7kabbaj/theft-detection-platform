from __future__ import annotations

import logging
import threading
import time
from collections import deque

import redis

from app.capture.buffer import CapturedFrame

logger = logging.getLogger(__name__)


class FramePublisher:
    def __init__(
        self,
        redis_url: str,
        stream_key: str,
        maxlen: int,
        queue_depth: int,
        retry_backoff_seconds: float,
        retry_backoff_max_seconds: float,
        connection_kwargs: dict[str, object] | None = None,
    ) -> None:
        self._redis_url = redis_url
        self._stream_key = stream_key
        self._maxlen = maxlen
        self._retry_backoff = retry_backoff_seconds
        self._retry_backoff_max = retry_backoff_max_seconds
        self._connection_kwargs = dict(connection_kwargs or {})
        self._queue: deque[CapturedFrame] = deque(maxlen=queue_depth)
        self._queue_lock = threading.Lock()
        self._wakeup = threading.Event()
        self._running = threading.Event()
        self._thread: threading.Thread | None = None
        self._client: redis.Redis | None = None
        self._client_lock = threading.Lock()
        self._published_total = 0
        self._failed_total = 0
        self._dropped_overflow_total = 0

    @property
    def counters(self) -> dict[str, int]:
        with self._queue_lock:
            return {
                "published_total": self._published_total,
                "failed_total": self._failed_total,
                "dropped_overflow_total": self._dropped_overflow_total,
                "queue_depth": len(self._queue),
            }

    def _get_client(self) -> redis.Redis:
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    pool = redis.ConnectionPool.from_url(
                        self._redis_url,
                        max_connections=4,
                        **self._connection_kwargs,
                    )
                    self._client = redis.Redis(connection_pool=pool)
        return self._client

    def push(self, frame: CapturedFrame) -> None:
        with self._queue_lock:
            if len(self._queue) == self._queue.maxlen:
                self._dropped_overflow_total += 1
            self._queue.append(frame)
        self._wakeup.set()

    def _pop(self) -> CapturedFrame | None:
        with self._queue_lock:
            if self._queue:
                return self._queue.popleft()
            self._wakeup.clear()
            return None

    def start(self) -> None:
        self._running.set()
        self._thread = threading.Thread(target=self._run, name="publisher", daemon=True)
        self._thread.start()
        logger.info("frame publisher started stream=%s maxlen=%d", self._stream_key, self._maxlen)

    def stop(self) -> None:
        self._running.clear()
        self._wakeup.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        if self._client is not None:
            self._client.close()
            self._client = None
        logger.info(
            "frame publisher stopped published=%d failed=%d dropped=%d",
            self._published_total,
            self._failed_total,
            self._dropped_overflow_total,
        )

    def _run(self) -> None:
        backoff = self._retry_backoff
        while self._running.is_set():
            frame = self._pop()
            if frame is None:
                self._wakeup.wait(timeout=1.0)
                continue
            try:
                client = self._get_client()
                client.xadd(
                    self._stream_key,
                    {
                        "payload": frame.payload,
                        "session_id": frame.session_id,
                        "frame_index": frame.frame_index,
                        "camera_id": frame.camera_id,
                        "timestamp_unix": frame.timestamp_unix,
                    },
                    maxlen=self._maxlen,
                    approximate=True,
                )
                with self._queue_lock:
                    self._published_total += 1
                backoff = self._retry_backoff
            except redis.exceptions.RedisError as exc:
                with self._queue_lock:
                    self._failed_total += 1
                logger.warning(
                    "publish failed error=%s, backing off %.1fs", type(exc).__name__, backoff
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, self._retry_backoff_max)
