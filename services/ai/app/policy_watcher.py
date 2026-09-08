from __future__ import annotations

import asyncio
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor

import redis.asyncio as redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

CURRENT_KEY = "policy:detection:current"
APPLIED_KEY = "policy:detection:applied"
CHANNEL = "policy:detection"


class PolicyWatcher:
    def __init__(
        self,
        redis_url: str,
        connection_kwargs: dict[str, object],
        detector,
        executor: ThreadPoolExecutor,
        device: str,
        retry_seconds: float = 5.0,
    ) -> None:
        self._redis_url = redis_url
        self._connection_kwargs = connection_kwargs
        self._detector = detector
        self._executor = executor
        self._device = device
        self._retry_seconds = retry_seconds
        self._client: redis.Redis | None = None
        self._stopping = asyncio.Event()
        self._version = 0

    async def _connect(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.from_url(self._redis_url, **self._connection_kwargs)
        return self._client

    async def _apply(self, raw: bytes | str) -> None:
        document = json.loads(raw)
        version = int(document["version"])
        if version <= self._version:
            return
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            self._executor,
            self._detector.apply_policy,
            document["policy"],
        )
        self._version = version
        await self._report(version)
        logger.info("detection policy applied version=%d", version)

    async def _report(self, version: int) -> None:
        client = await self._connect()
        try:
            await client.hset(
                APPLIED_KEY,
                mapping={
                    "version": str(version),
                    "applied_at": str(time.time()),
                    "device": self._device,
                },
            )
        except RedisError as exc:
            logger.warning("applied policy report failed version=%d: %s", version, exc)

    async def prime(self) -> None:
        try:
            client = await self._connect()
            raw = await client.get(CURRENT_KEY)
        except RedisError as exc:
            logger.warning("detection policy read failed, running on env defaults: %s", exc)
            return
        if raw is None:
            logger.info("no stored detection policy, running on env defaults")
            return
        await self._apply(raw)

    async def run(self) -> None:
        while not self._stopping.is_set():
            try:
                client = await self._connect()
                pubsub = client.pubsub()
                await pubsub.subscribe(CHANNEL)
                logger.info("detection policy watcher subscribed channel=%s", CHANNEL)
                async for message in pubsub.listen():
                    if self._stopping.is_set():
                        break
                    if message.get("type") != "message":
                        continue
                    try:
                        await self._apply(message["data"])
                    except (ValueError, KeyError, TypeError) as exc:
                        logger.error("detection policy message rejected: %s", exc)
            except (RedisError, OSError) as exc:
                if self._stopping.is_set():
                    break
                logger.warning("detection policy watcher reconnecting: %s", exc)
                self._client = None
                await asyncio.sleep(self._retry_seconds)

    async def stop(self) -> None:
        self._stopping.set()
        if self._client is not None:
            await self._client.aclose()
            self._client = None
