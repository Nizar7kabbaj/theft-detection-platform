from __future__ import annotations

import asyncio
import contextlib
import logging

from redis.asyncio import Redis
from redis.asyncio.client import PubSub
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

REVOCATION_CHANNEL = "session:revoked"


class RevocationService:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._sessions: dict[str, set[asyncio.Event]] = {}
        self._pubsub: PubSub | None = None
        self._listener_task: asyncio.Task[None] | None = None

    @property
    def tracked_sessions(self) -> int:
        return len(self._sessions)

    def register(self, session_id: str) -> asyncio.Event:
        flag = asyncio.Event()
        self._sessions.setdefault(session_id, set()).add(flag)
        return flag

    def unregister(self, session_id: str, flag: asyncio.Event) -> None:
        holders = self._sessions.get(session_id)
        if holders is None:
            return
        holders.discard(flag)
        if not holders:
            self._sessions.pop(session_id, None)

    async def start(self) -> None:
        self._pubsub = self._redis.pubsub()
        await self._pubsub.subscribe(REVOCATION_CHANNEL)
        self._listener_task = asyncio.create_task(
            self._listen(), name="session-revocation-listener"
        )
        logger.info("revocation listener started channel=%s", REVOCATION_CHANNEL)

    async def stop(self) -> None:
        if self._listener_task is not None:
            self._listener_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._listener_task
        if self._pubsub is not None:
            with contextlib.suppress(RedisError):
                await self._pubsub.unsubscribe()
            await self._pubsub.aclose()
        self._sessions.clear()
        logger.info("revocation listener stopped")

    async def _listen(self) -> None:
        pubsub = self._pubsub
        if pubsub is None:
            return
        while True:
            try:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message is None:
                    continue
                if message["type"] != "message":
                    continue
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode()
                self._trip(data)
            except asyncio.CancelledError:
                raise
            except RedisError as exc:
                logger.error("revocation listener error: %s", exc)
                await asyncio.sleep(0.5)

    def _trip(self, session_id: str) -> None:
        holders = self._sessions.get(session_id)
        if not holders:
            return
        for flag in holders:
            flag.set()
        logger.info("session revoked sockets=%d", len(holders))
