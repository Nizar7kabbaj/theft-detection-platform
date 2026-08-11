from __future__ import annotations

import asyncio
import contextlib
import logging
import signal

import grpc

from app.capture.buffer import ForwardBuffer
from app.capture.device import CameraDevice
from app.capture.forwarder import Forwarder
from app.capture.loop import CaptureLoop
from app.capture.publisher import FramePublisher
from app.capture.rate import RateController
from app.core.config import Settings, get_settings
from app.observability import register_capture_metrics, setup_observability


def _channel_credentials(settings: Settings) -> grpc.ChannelCredentials:
    return grpc.ssl_channel_credentials(
        root_certificates=settings.TLS_CA_FILE.read_bytes(),
        private_key=settings.TLS_KEY_FILE.read_bytes(),
        certificate_chain=settings.TLS_CERT_FILE.read_bytes(),
    )


async def _serve() -> None:
    setup_observability(service_name="theft-camera")
    settings = get_settings()
    logging.getLogger().setLevel(settings.LOG_LEVEL)
    log = logging.getLogger("app.main")
    log.info("starting camera service camera=%s", settings.CAMERA_ID)
    device = CameraDevice(
        device_path=settings.DEVICE_PATH,
        frame_width=settings.FRAME_WIDTH,
        frame_height=settings.FRAME_HEIGHT,
        target_fps=settings.ACTIVE_FPS,
        reopen_backoff_seconds=settings.DEVICE_REOPEN_BACKOFF_SECONDS,
        reopen_backoff_max_seconds=settings.DEVICE_REOPEN_BACKOFF_MAX_SECONDS,
    )
    buffer = ForwardBuffer(
        max_depth=settings.BUFFER_MAX_DEPTH,
        max_age_seconds=settings.BUFFER_MAX_AGE_SECONDS,
    )
    publisher = FramePublisher(
        redis_url=settings.REDIS_URL,
        connection_kwargs=settings.redis_tls_options,
        stream_key=settings.frame_stream_key,
        maxlen=settings.FRAME_STREAM_MAXLEN,
        queue_depth=settings.PUBLISH_QUEUE_DEPTH,
        retry_backoff_seconds=settings.PUBLISH_RETRY_BACKOFF_SECONDS,
        retry_backoff_max_seconds=settings.PUBLISH_RETRY_BACKOFF_MAX_SECONDS,
    )
    loop = CaptureLoop(
        device=device,
        buffer=buffer,
        publisher=publisher,
        camera_id=settings.CAMERA_ID,
        target_fps=settings.IDLE_FPS,
        heartbeat_path=settings.HEARTBEAT_PATH,
    )
    rate_controller = RateController(
        set_pace=loop.set_pace,
        idle_fps=settings.IDLE_FPS,
        active_fps=settings.ACTIVE_FPS,
        dwell_seconds=settings.DWELL_SECONDS,
    )
    forwarder = Forwarder(
        buffer=buffer,
        target=settings.ai_target,
        retry_backoff_seconds=settings.FORWARD_RETRY_BACKOFF_SECONDS,
        retry_backoff_max_seconds=settings.FORWARD_RETRY_BACKOFF_MAX_SECONDS,
        rate_controller=rate_controller,
        credentials=_channel_credentials(settings),
    )
    register_capture_metrics(
        camera_id=settings.CAMERA_ID,
        buffer_counters=lambda: buffer.counters,
        forward_counters=lambda: forwarder.counters,
        publish_counters=lambda: publisher.counters,
        buffer_depth=lambda: buffer.depth,
        target_fps=lambda: rate_controller.current_fps,
    )
    stop_event = asyncio.Event()
    running_loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        running_loop.add_signal_handler(sig, stop_event.set)
    publisher.start()
    loop.start()
    forward_task = asyncio.create_task(forwarder.run())
    log.info("camera service running")
    await stop_event.wait()
    log.info("shutdown signal received")
    await forwarder.stop()
    forward_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await forward_task
    loop.stop()
    publisher.stop()
    log.info("camera service stopped")


def main() -> None:
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
