from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import grpc

from app.capture.camera_source import CameraFrameSource
from app.capture.detector import PersonDetector
from app.capture.frame_source import ClipFrameSource, FrameSource
from app.capture.presence import PresenceEdge, PresenceState, PresenceStateMachine
from app.capture.presence_client import PresenceClient
from app.core.config import Settings, get_settings
from app.observability import register_gate_metrics, setup_observability


def _channel_credentials(settings: Settings) -> grpc.ChannelCredentials:
    return grpc.ssl_channel_credentials(
        root_certificates=settings.TLS_CA_FILE.read_bytes(),
        private_key=settings.TLS_KEY_FILE.read_bytes(),
        certificate_chain=settings.TLS_CERT_FILE.read_bytes(),
    )


_STATE_TO_GAUGE = {
    PresenceState.UNKNOWN: 0,
    PresenceState.ABSENT: 0,
    PresenceState.PRESENT: 1,
}


class GateCounters:
    def __init__(self) -> None:
        self.frames_processed_total = 0
        self.person_detections_total = 0
        self.entries_total = 0
        self.exits_total = 0

    def snapshot(self) -> dict[str, int]:
        return {
            "frames_processed_total": self.frames_processed_total,
            "person_detections_total": self.person_detections_total,
            "entries_total": self.entries_total,
            "exits_total": self.exits_total,
        }


def _touch(path: Path) -> None:
    path.touch()


async def _frame_loop(
    source: FrameSource,
    detector: PersonDetector,
    machine: PresenceStateMachine,
    client: PresenceClient,
    counters: GateCounters,
    pool: ThreadPoolExecutor,
    camera_id: str,
    heartbeat_path: Path,
    heartbeat_interval: float,
    stop_event: asyncio.Event,
) -> None:
    loop = asyncio.get_running_loop()
    frame_index = 0
    last_heartbeat = 0.0
    log = logging.getLogger("app.gate")
    while not stop_event.is_set():
        _touch(heartbeat_path)
        frame = await source.read()
        if frame is None:
            continue
        result = await loop.run_in_executor(pool, detector.detect, frame)
        counters.frames_processed_total += 1
        frame_index += 1
        now = time.monotonic()
        if now - last_heartbeat >= heartbeat_interval:
            client.heartbeat(frame_index)
            last_heartbeat = now
        if result.person_seen:
            counters.person_detections_total += 1
        edge = machine.observe(result.person_seen)
        if edge is PresenceEdge.ENTERED:
            counters.entries_total += 1
            client.submit(edge, result.top_confidence, frame_index)
            log.info("person entered camera=%s frame=%d", camera_id, frame_index)
        elif edge is PresenceEdge.LEFT:
            if machine.cold_start_absent:
                client.submit(edge, result.top_confidence, frame_index)
                log.info("room empty at start camera=%s frame=%d", camera_id, frame_index)
            else:
                counters.exits_total += 1
                client.submit(edge, result.top_confidence, frame_index)
                log.info("person left camera=%s frame=%d", camera_id, frame_index)


async def _serve() -> None:
    setup_observability(service_name="theft-detect-gate")
    settings = get_settings()
    logging.getLogger().setLevel(settings.LOG_LEVEL)
    log = logging.getLogger("app.main")
    log.info("starting detect-gate camera=%s", settings.CAMERA_ID)
    source: FrameSource
    if settings.FRAME_SOURCE == "camera":
        source = CameraFrameSource(
            redis_url=settings.REDIS_URL,
            connection_kwargs=settings.redis_tls_options,
            stream_key=settings.frame_stream_key,
            read_block_ms=settings.FRAME_READ_BLOCK_MS,
            retry_backoff_seconds=settings.FRAME_RETRY_BACKOFF_SECONDS,
            retry_backoff_max_seconds=settings.FRAME_RETRY_BACKOFF_MAX_SECONDS,
        )
        log.info("frame source camera stream=%s", settings.frame_stream_key)
    else:
        source = ClipFrameSource(clip_path=settings.CLIP_PATH, target_fps=settings.GATE_FPS)
        log.info("frame source clip path=%s", settings.CLIP_PATH)
    detector = PersonDetector(
        model_name=settings.MODEL_NAME,
        device=settings.MODEL_DEVICE,
        person_class=settings.PERSON_CLASS_ID,
        confidence=settings.DETECTION_CONFIDENCE,
    )
    detector.load()
    log.info("detector loaded device=%s", detector.device)
    machine = PresenceStateMachine(exit_debounce_frames=settings.EXIT_DEBOUNCE_FRAMES)
    client = PresenceClient(
        target=settings.ai_target,
        camera_id=settings.CAMERA_ID,
        session_id=settings.SESSION_ID,
        connect_timeout_seconds=settings.STREAM_SEND_TIMEOUT_SECONDS,
        retry_backoff_seconds=settings.STREAM_RETRY_BACKOFF_SECONDS,
        retry_backoff_max_seconds=settings.STREAM_RETRY_BACKOFF_MAX_SECONDS,
        credentials=_channel_credentials(settings),
    )
    counters = GateCounters()
    register_gate_metrics(
        camera_id=settings.CAMERA_ID,
        presence_value=lambda: _STATE_TO_GAUGE[machine.state],
        gate_counters=counters.snapshot,
        stream_counters=lambda: client.counters,
    )
    await asyncio.to_thread(_touch, settings.HEARTBEAT_PATH)
    pool = ThreadPoolExecutor(max_workers=1)
    stop_event = asyncio.Event()
    running_loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        running_loop.add_signal_handler(sig, stop_event.set)
    client_task = asyncio.create_task(client.run())
    loop_task = asyncio.create_task(
        _frame_loop(
            source,
            detector,
            machine,
            client,
            counters,
            pool,
            settings.CAMERA_ID,
            settings.HEARTBEAT_PATH,
            settings.HEARTBEAT_INTERVAL_SECONDS,
            stop_event,
        )
    )
    log.info("detect-gate running")
    await stop_event.wait()
    log.info("shutdown signal received")
    loop_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await loop_task
    await client.stop()
    client_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await client_task
    await source.close()
    detector.close()
    pool.shutdown(wait=False)
    log.info("detect-gate stopped")


def main() -> None:
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
