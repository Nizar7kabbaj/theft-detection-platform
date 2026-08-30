from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable

from redis import asyncio as aioredis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


class StatsPublisher:
    def __init__(
        self,
        redis_url: str,
        stats_key: str,
        interval_seconds: float,
        ttl_seconds: int,
        published_total: Callable[[], int],
        latency_ms: Callable[[], float | None],
        target_fps: Callable[[], float],
        connection_kwargs: dict[str, object] | None = None,
    ) -> None:
        self._redis_url = redis_url
        self._stats_key = stats_key
        self._interval = interval_seconds
        self._ttl = ttl_seconds
        self._published_total = published_total
        self._latency_ms = latency_ms
        self._target_fps = target_fps
        self._connection_kwargs = dict(connection_kwargs or {})
        self._client: aioredis.Redis | None = None
        self._running = False
        self._written_total = 0
        self._failed_total = 0

    @property
    def counters(self) -> dict[str, int]:
        return {
            "written_total": self._written_total,
            "failed_total": self._failed_total,
        }

    def _get_client(self) -> aioredis.Redis:
        if self._client is None:
            pool = aioredis.ConnectionPool.from_url(
                self._redis_url,
                max_connections=2,
                **self._connection_kwargs,
            )
            self._client = aioredis.Redis(connection_pool=pool)
        return self._client

    async def _write(self, fps: float) -> None:
        latency = self._latency_ms()
        body = json.dumps(
            {
                "fps": round(fps, 2),
                "target_fps": round(self._target_fps(), 2),
                "latency_ms": None if latency is None else round(latency, 1),
                "updated_at": time.time(),
            }
        )
        try:
            client = self._get_client()
            await client.set(self._stats_key, body, ex=self._ttl)
            self._written_total += 1
        except RedisError as exc:
            self._failed_total += 1
            logger.warning("stats write failed error=%s", type(exc).__name__)

    async def run(self) -> None:
        self._running = True
        last_count = self._published_total()
        last_at = time.monotonic()
        while self._running:
            await asyncio.sleep(self._interval)
            now = time.monotonic()
            count = self._published_total()
            elapsed = now - last_at
            if elapsed <= 0:
                continue
            fps = max(0.0, (count - last_count) / elapsed)
            last_count = count
            last_at = now
            await self._write(fps)

    async def stop(self) -> None:
        self._running = False
        if self._client is not None:
            await self._client.aclose()
            self._client = None
