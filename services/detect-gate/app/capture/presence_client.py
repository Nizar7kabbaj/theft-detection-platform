from __future__ import annotations

import asyncio
import logging

import grpc
from google.protobuf.timestamp_pb2 import Timestamp

from app.capture.presence import PresenceEdge
from app.grpc_gen import presence_pb2, presence_pb2_grpc

logger = logging.getLogger(__name__)
_EDGE_TO_KIND = {
    PresenceEdge.ENTERED: presence_pb2.PRESENCE_EVENT_KIND_PERSON_ENTERED,
    PresenceEdge.LEFT: presence_pb2.PRESENCE_EVENT_KIND_PERSON_LEFT,
}


class PresenceClient:
    def __init__(
        self,
        target: str,
        camera_id: str,
        session_id: int,
        connect_timeout_seconds: float,
        retry_backoff_seconds: float,
        retry_backoff_max_seconds: float,
        credentials: grpc.ChannelCredentials,
        queue_max_depth: int = 64,
    ) -> None:
        self._target = target
        self._credentials = credentials
        self._camera_id = camera_id
        self._session_id = session_id
        self._connect_timeout = connect_timeout_seconds
        self._retry_backoff = retry_backoff_seconds
        self._retry_backoff_max = retry_backoff_max_seconds
        self._queue: asyncio.Queue[presence_pb2.PresenceEvent] = asyncio.Queue(
            maxsize=queue_max_depth
        )
        self._channel: grpc.aio.Channel | None = None
        self._stub: presence_pb2_grpc.PresenceServiceStub | None = None
        self._running = False
        self._event_seq = 0
        self._heartbeats_dropped = 0
        self._events_sent = 0
        self._acks_received = 0
        self._stream_failures = 0

    @property
    def counters(self) -> dict[str, int]:
        return {
            "events_sent_total": self._events_sent,
            "acks_received_total": self._acks_received,
            "stream_failures_total": self._stream_failures,
        }

    def _build(
        self,
        kind: int,
        confidence: float,
        frame_index: int,
    ) -> presence_pb2.PresenceEvent:
        self._event_seq += 1
        ts = Timestamp()
        ts.GetCurrentTime()
        return presence_pb2.PresenceEvent(
            event_id=f"{self._camera_id}-{self._session_id}-{self._event_seq}",
            kind=kind,
            occurred_at=ts,
            camera_id=self._camera_id,
            session_id=self._session_id,
            detection_confidence=confidence,
            source_frame_index=frame_index,
        )

    def submit(self, edge: PresenceEdge, confidence: float, frame_index: int) -> None:
        kind = _EDGE_TO_KIND.get(edge)
        if kind is None:
            return
        event = self._build(kind, confidence, frame_index)
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            _ = self._queue.get_nowait()
            self._queue.put_nowait(event)
            logger.warning("presence queue full, dropped oldest event")

    def heartbeat(self, frame_index: int) -> None:
        event = self._build(presence_pb2.PRESENCE_EVENT_KIND_HEARTBEAT, 0.0, frame_index)
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            self._heartbeats_dropped += 1
            logger.debug("presence queue full, heartbeat dropped")

    async def _outbound(self):
        while self._running:
            event = await self._queue.get()
            self._events_sent += 1
            yield event

    def _connect(self) -> None:
        self._channel = grpc.aio.secure_channel(self._target, self._credentials)
        self._stub = presence_pb2_grpc.PresenceServiceStub(self._channel)

    async def _disconnect(self) -> None:
        if self._channel is not None:
            await self._channel.close()
            self._channel = None
            self._stub = None

    async def run(self) -> None:
        self._running = True
        backoff = self._retry_backoff
        while self._running:
            self._connect()
            try:
                await asyncio.wait_for(self._channel.channel_ready(), timeout=self._connect_timeout)
                logger.info("presence stream connected target=%s", self._target)
                backoff = self._retry_backoff
                call = self._stub.StreamPresence(self._outbound())
                async for ack in call:
                    self._acks_received += 1
                    logger.debug("presence ack event=%s status=%s", ack.event_id, ack.status)
            except (TimeoutError, grpc.aio.AioRpcError) as exc:
                self._stream_failures += 1
                reason = (
                    exc.code().name if isinstance(exc, grpc.aio.AioRpcError) else "connect timeout"
                )
                logger.warning("presence stream lost reason=%s, backing off %.1fs", reason, backoff)
                await self._disconnect()
                if not self._running:
                    break
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self._retry_backoff_max)

    async def stop(self) -> None:
        self._running = False
        await self._disconnect()
        logger.info(
            "presence client stopped sent=%d acks=%d failures=%d",
            self._events_sent,
            self._acks_received,
            self._stream_failures,
        )
