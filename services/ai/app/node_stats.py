from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time

import pynvml
from redis import asyncio as aioredis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


class NodeStatsPublisher:
    def __init__(
        self,
        redis_url: str,
        stats_key: str,
        interval_seconds: float,
        ttl_seconds: int,
        device_index: int = 0,
        connection_kwargs: dict[str, object] | None = None,
    ) -> None:
        self._redis_url = redis_url
        self._stats_key = stats_key
        self._interval = interval_seconds
        self._ttl = ttl_seconds
        self._device_index = device_index
        self._connection_kwargs = dict(connection_kwargs or {})
        self._client: aioredis.Redis | None = None
        self._handle: object | None = None
        self._device_name: str | None = None
        self._running = False
        self._written_total = 0
        self._failed_total = 0

    @property
    def counters(self) -> dict[str, int]:
        return {
            "written_total": self._written_total,
            "failed_total": self._failed_total,
        }

    def _open_device(self) -> bool:
        try:
            pynvml.nvmlInit()
            self._handle = pynvml.nvmlDeviceGetHandleByIndex(self._device_index)
            name = pynvml.nvmlDeviceGetName(self._handle)
            self._device_name = name.decode() if isinstance(name, bytes) else str(name)
        except pynvml.NVMLError as exc:
            logger.warning("gpu sensor unavailable error=%s", type(exc).__name__)
            self._handle = None
            return False
        logger.info("gpu sensor ready device=%s", self._device_name)
        return True

    def _close_device(self) -> None:
        if self._handle is None:
            return
        self._handle = None
        with contextlib.suppress(pynvml.NVMLError):
            pynvml.nvmlShutdown()

    def _sample(self) -> dict[str, object] | None:
        if self._handle is None:
            return None
        try:
            temperature = pynvml.nvmlDeviceGetTemperature(self._handle, pynvml.NVML_TEMPERATURE_GPU)
            utilization = pynvml.nvmlDeviceGetUtilizationRates(self._handle)
        except pynvml.NVMLError as exc:
            logger.warning("gpu read failed error=%s", type(exc).__name__)
            return None
        return {
            "gpu_name": self._device_name,
            "gpu_temperature_c": int(temperature),
            "gpu_utilization_pct": int(utilization.gpu),
            "updated_at": time.time(),
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

    async def _write(self, reading: dict[str, object]) -> None:
        try:
            client = self._get_client()
            await client.set(self._stats_key, json.dumps(reading), ex=self._ttl)
            self._written_total += 1
        except RedisError as exc:
            self._failed_total += 1
            logger.warning("node stats write failed error=%s", type(exc).__name__)

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        if not await loop.run_in_executor(None, self._open_device):
            return
        self._running = True
        while self._running:
            reading = await loop.run_in_executor(None, self._sample)
            if reading is not None:
                await self._write(reading)
            await asyncio.sleep(self._interval)

    async def stop(self) -> None:
        self._running = False
        self._close_device()
        if self._client is not None:
            await self._client.aclose()
            self._client = None
