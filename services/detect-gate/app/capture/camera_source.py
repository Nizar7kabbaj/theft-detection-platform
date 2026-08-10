from __future__ import annotations

import asyncio
import contextlib
import logging
import time

import cv2
import numpy as np
import redis

logger = logging.getLogger(__name__)


class CameraFrameSource:
    def __init__(
        self,
        redis_url: str,
        stream_key: str,
        read_block_ms: int,
        retry_backoff_seconds: float,
        retry_backoff_max_seconds: float,
        connection_kwargs: dict[str, object] | None = None,
    ) -> None:
        self._redis_url = redis_url
        self._stream_key = stream_key
        self._read_block_ms = read_block_ms
        self._retry_backoff = retry_backoff_seconds
        self._retry_backoff_max = retry_backoff_max_seconds
        self._connection_kwargs = dict(connection_kwargs or {})
        self._backoff = retry_backoff_seconds
        self._client: redis.Redis | None = None
        self._connected_logged = False

    def _get_client(self) -> redis.Redis:
        if self._client is None:
            pool = redis.ConnectionPool.from_url(
                self._redis_url,
                max_connections=4,
                **self._connection_kwargs,
            )
            self._client = redis.Redis(connection_pool=pool)
        return self._client

    def _drop_client(self) -> None:
        if self._client is not None:
            with contextlib.suppress(redis.exceptions.RedisError):
                self._client.close()
            self._client = None
        self._connected_logged = False

    def _read_blocking(self) -> np.ndarray | None:
        try:
            client = self._get_client()
            res = client.xread({self._stream_key: "$"}, count=1, block=self._read_block_ms)
            if not self._connected_logged:
                logger.info("frame source connected stream=%s", self._stream_key)
                self._connected_logged = True
            self._backoff = self._retry_backoff
            if not res:
                return None
            _, entries = res[0]
            _, fields = entries[0]
            payload = fields.get(b"payload")
            if payload is None:
                return None
            frame = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                logger.warning(
                    "frame decode failed stream=%s bytes=%d", self._stream_key, len(payload)
                )
            return frame
        except redis.exceptions.RedisError as exc:
            logger.warning(
                "frame read failed error=%s, backing off %.1fs", type(exc).__name__, self._backoff
            )
            self._drop_client()
            time.sleep(self._backoff)
            self._backoff = min(self._backoff * 2, self._retry_backoff_max)
            return None

    async def read(self) -> np.ndarray | None:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._read_blocking)

    async def close(self) -> None:
        self._drop_client()
