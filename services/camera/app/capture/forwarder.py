from __future__ import annotations

import asyncio
import logging

import grpc
from google.protobuf.timestamp_pb2 import Timestamp

from app.capture.buffer import CapturedFrame, ForwardBuffer
from app.capture.rate import RateController
from app.grpc_gen import inference_pb2, inference_pb2_grpc

logger = logging.getLogger(__name__)


class Forwarder:
    def __init__(
        self,
        buffer: ForwardBuffer,
        target: str,
        retry_backoff_seconds: float,
        retry_backoff_max_seconds: float,
        rate_controller: RateController,
        credentials: grpc.ChannelCredentials,
    ) -> None:
        self._buffer = buffer
        self._target = target
        self._credentials = credentials
        self._retry_backoff = retry_backoff_seconds
        self._retry_backoff_max = retry_backoff_max_seconds
        self._rate_controller = rate_controller
        self._channel: grpc.aio.Channel | None = None
        self._stub: inference_pb2_grpc.InferenceServiceStub | None = None
        self._running = False
        self._forwarded_total = 0
        self._failed_total = 0

    @property
    def counters(self) -> dict[str, int]:
        return {
            "forwarded_total": self._forwarded_total,
            "failed_total": self._failed_total,
        }

    def _connect(self) -> None:
        self._channel = grpc.aio.secure_channel(self._target, self._credentials)
        self._stub = inference_pb2_grpc.InferenceServiceStub(self._channel)
        logger.info("forwarder connected target=%s", self._target)

    async def _disconnect(self) -> None:
        if self._channel is not None:
            await self._channel.close()
            self._channel = None
            self._stub = None

    def _to_proto(self, record: CapturedFrame) -> inference_pb2.Frame:
        ts = Timestamp()
        ts.FromMilliseconds(int(record.timestamp_unix * 1000))
        return inference_pb2.Frame(
            payload=record.payload,
            session_id=record.session_id,
            frame_index=record.frame_index,
            timestamp=ts,
            camera_id=record.camera_id,
        )

    async def run(self, idle_sleep: float = 0.02) -> None:
        self._running = True
        self._connect()
        backoff = self._retry_backoff
        while self._running:
            record = self._buffer.pop_fresh()
            if record is None:
                await asyncio.sleep(idle_sleep)
                continue
            try:
                detection = await self._stub.Analyze(self._to_proto(record), timeout=1.0)
                self._forwarded_total += 1
                backoff = self._retry_backoff
                self._rate_controller.observe(detection.detection_present)
            except grpc.aio.AioRpcError as exc:
                self._failed_total += 1
                logger.warning(
                    "forward failed code=%s, backing off %.1fs", exc.code().name, backoff
                )
                await self._disconnect()
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self._retry_backoff_max)
                self._connect()

    async def stop(self) -> None:
        self._running = False
        await self._disconnect()
        logger.info(
            "forwarder stopped forwarded=%d failed=%d", self._forwarded_total, self._failed_total
        )
