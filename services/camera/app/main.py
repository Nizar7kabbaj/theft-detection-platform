from __future__ import annotations

import asyncio
import logging
import signal

from app.core.config import get_settings
from app.observability import register_capture_metrics, setup_observability
from app.capture.buffer import ForwardBuffer
from app.capture.device import CameraDevice
from app.capture.forwarder import Forwarder
from app.capture.loop import CaptureLoop


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
        target_fps=settings.TARGET_FPS,
        reopen_backoff_seconds=settings.DEVICE_REOPEN_BACKOFF_SECONDS,
        reopen_backoff_max_seconds=settings.DEVICE_REOPEN_BACKOFF_MAX_SECONDS,
    )
    buffer = ForwardBuffer(
        max_depth=settings.BUFFER_MAX_DEPTH,
        max_age_seconds=settings.BUFFER_MAX_AGE_SECONDS,
    )
    loop = CaptureLoop(
        device=device,
        buffer=buffer,
        camera_id=settings.CAMERA_ID,
        target_fps=settings.TARGET_FPS,
        jpeg_quality=settings.JPEG_QUALITY,
        heartbeat_path=settings.HEARTBEAT_PATH,
    )
    forwarder = Forwarder(
        buffer=buffer,
        target=settings.ai_target,
        retry_backoff_seconds=settings.FORWARD_RETRY_BACKOFF_SECONDS,
        retry_backoff_max_seconds=settings.FORWARD_RETRY_BACKOFF_MAX_SECONDS,
    )

    register_capture_metrics(
        camera_id=settings.CAMERA_ID,
        buffer_counters=lambda: buffer.counters,
        forward_counters=lambda: forwarder.counters,
        buffer_depth=lambda: buffer.depth,
    )

    stop_event = asyncio.Event()
    running_loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        running_loop.add_signal_handler(sig, stop_event.set)

    loop.start()
    forward_task = asyncio.create_task(forwarder.run())
    log.info("camera service running")

    await stop_event.wait()
    log.info("shutdown signal received")

    await forwarder.stop()
    forward_task.cancel()
    try:
        await forward_task
    except asyncio.CancelledError:
        pass
    loop.stop()
    log.info("camera service stopped")


def main() -> None:
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
