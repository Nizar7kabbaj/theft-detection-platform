from __future__ import annotations

import asyncio
import contextlib
import json
import logging

from fastapi import WebSocket
from redis.asyncio import Redis
from redis.asyncio.client import PubSub
from starlette.websockets import WebSocketState

logger = logging.getLogger(__name__)

_TOPIC_PATTERNS: dict[str, str] = {
    "alerts": "alerts:*",
    "cameras": "cameras:*",
}


class BroadcastService:
    def __init__(
        self,
        redis: Redis,
        max_connections: int,
        heartbeat_seconds: int,
    ) -> None:
        self._redis = redis
        self._max = max_connections
        self._heartbeat = heartbeat_seconds
        self._connections: dict[str, set[WebSocket]] = {topic: set() for topic in _TOPIC_PATTERNS}
        self._pubsub: PubSub | None = None
        self._listener_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None

    @property
    def total_connections(self) -> int:
        return sum(len(s) for s in self._connections.values())

    async def start(self) -> None:
        self._pubsub = self._redis.pubsub()
        await self._pubsub.psubscribe(*_TOPIC_PATTERNS.values())
        self._listener_task = asyncio.create_task(self._listen(), name="ws-broadcast-listener")
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(), name="ws-broadcast-heartbeat"
        )
        logger.info(
            "broadcaster started patterns=%s",
            list(_TOPIC_PATTERNS.values()),
        )

    async def stop(self) -> None:
        for task in (self._listener_task, self._heartbeat_task):
            if task is None:
                continue
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if self._pubsub is not None:
            await self._pubsub.punsubscribe()
            await self._pubsub.aclose()
        for topic in list(self._connections):
            for ws in list(self._connections[topic]):
                try:
                    await ws.close()
                except Exception:
                    logger.debug("websocket close during shutdown failed", exc_info=True)
            self._connections[topic].clear()
        logger.info("broadcaster stopped")

    async def register(self, ws: WebSocket, topic: str) -> bool:
        if topic not in self._connections:
            await ws.close(code=1003, reason="unknown topic")
            return False
        if self.total_connections >= self._max:
            await ws.close(code=1008, reason="connection limit reached")
            logger.warning("rejected websocket cap=%d reached", self._max)
            return False
        self._connections[topic].add(ws)
        logger.info(
            "websocket registered topic=%s total=%d",
            topic,
            self.total_connections,
        )
        return True

    def unregister(self, ws: WebSocket, topic: str) -> None:
        self._connections.get(topic, set()).discard(ws)
        logger.info(
            "websocket unregistered topic=%s total=%d",
            topic,
            self.total_connections,
        )

    async def _listen(self) -> None:
        pubsub = self._pubsub
        if pubsub is None:
            return
        while True:
            try:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message is None:
                    continue
                if message["type"] not in ("message", "pmessage"):
                    continue
                channel = message["channel"]
                data = message["data"]
                if isinstance(channel, bytes):
                    channel = channel.decode()
                if isinstance(data, bytes):
                    data = data.decode()
                await self._dispatch(channel, data)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("broadcaster listen error: %s", exc)
                await asyncio.sleep(0.5)

    async def _dispatch(self, channel: str, raw: str) -> None:
        topic, _, event = channel.partition(":")
        if topic not in self._connections:
            return
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("dropping non-json pubsub message channel=%s", channel)
            return
        envelope = json.dumps({"event": event, "data": payload})
        for ws in list(self._connections[topic]):
            if ws.client_state != WebSocketState.CONNECTED:
                self._connections[topic].discard(ws)
                continue
            try:
                await ws.send_text(envelope)
            except Exception as exc:
                logger.warning("send failed dropping connection: %s", exc)
                self._connections[topic].discard(ws)

    async def _heartbeat_loop(self) -> None:
        ping = json.dumps({"event": "ping"})
        while True:
            try:
                await asyncio.sleep(self._heartbeat)
                for topic in list(self._connections):
                    for ws in list(self._connections[topic]):
                        if ws.client_state != WebSocketState.CONNECTED:
                            self._connections[topic].discard(ws)
                            continue
                        try:
                            await ws.send_text(ping)
                        except Exception:
                            self._connections[topic].discard(ws)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("heartbeat loop error: %s", exc)
