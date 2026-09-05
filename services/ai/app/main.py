from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
from concurrent.futures import ThreadPoolExecutor

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

from app.alert_client import AlertClient
from app.core.config import settings
from app.grpc_gen import inference_pb2_grpc, presence_pb2_grpc
from app.inference import LSTMDetector
from app.node_stats import NodeStatsPublisher
from app.observability import register_presence_gauge, setup_observability
from app.presence_servicer import PresenceServicer
from app.server.interceptors import IdentityInterceptor
from app.servicer import InferenceServicer

INFERENCE_SERVICE_FULL_NAME = "theftdetection.v1.InferenceService"
PRESENCE_SERVICE_FULL_NAME = "theftdetection.v1.PresenceService"


def _server_credentials() -> grpc.ServerCredentials:
    key = settings.TLS_KEY_FILE.read_bytes()
    cert = settings.TLS_CERT_FILE.read_bytes()
    ca = settings.TLS_CA_FILE.read_bytes()
    return grpc.ssl_server_credentials(
        [(key, cert)],
        root_certificates=ca,
        require_client_auth=settings.TLS_REQUIRE_CLIENT_AUTH,
    )


class AsyncHealthServicer(health.HealthServicer):
    async def Check(self, request, context):
        return super().Check(request, context)

    async def Watch(self, request, context):
        async for response in self._async_watch(request, context):
            yield response

    async def _async_watch(self, request, context):
        for response in super().Watch(request, context):
            yield response


async def _serve() -> None:
    setup_observability(service_name="theft-ai")
    logging.getLogger().setLevel(settings.LOG_LEVEL)
    log = logging.getLogger("app.main")
    log.info("starting ai service")
    executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="inference")
    detector = LSTMDetector(
        yolo_model_name=settings.YOLO_MODEL_NAME,
        object_model_name=settings.YOLO_OBJECT_MODEL_NAME,
        lstm_model_path=settings.LSTM_MODEL_PATH,
        device=settings.DEVICE,
        anomaly_threshold=settings.ANOMALY_THRESHOLD,
        person_class=settings.YOLO_PERSON_CLASS,
        person_confidence=settings.PERSON_CONFIDENCE,
        object_classes=settings.object_class_ids,
        object_confidence=settings.OBJECT_CONFIDENCE,
        grab_ratio=settings.CONCEALMENT_GRAB_RATIO,
        missing_frames=settings.CONCEALMENT_MISSING_FRAMES,
        keypoint_confidence=settings.CONCEALMENT_KEYPOINT_CONFIDENCE,
        expiry_frames=settings.CONCEALMENT_EXPIRY_FRAMES,
        snapshot_dir=settings.SNAPSHOT_DIR,
    )
    alert_client = AlertClient(
        api_base_url=settings.API_BASE_URL,
        auth_base_url=settings.AUTH_BASE_URL,
        username=settings.ALERT_USERNAME,
        password_file=settings.ALERT_PASSWORD_FILE,
        access_cookie_name=settings.ACCESS_COOKIE_NAME,
        csrf_cookie_name=settings.CSRF_COOKIE_NAME,
        csrf_header_name=settings.CSRF_HEADER_NAME,
        verify=True,
        timeout_seconds=settings.ALERT_TIMEOUT_SECONDS,
    )
    node_stats = NodeStatsPublisher(
        redis_url=settings.REDIS_URL,
        connection_kwargs=settings.redis_tls_options,
        stats_key=settings.NODE_STATS_KEY,
        interval_seconds=settings.NODE_STATS_INTERVAL_SECONDS,
        ttl_seconds=settings.NODE_STATS_TTL_SECONDS,
        device_index=settings.NODE_STATS_DEVICE_INDEX,
    )
    server = grpc.aio.server(interceptors=[IdentityInterceptor()])
    health_servicer = AsyncHealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    health_servicer.set(INFERENCE_SERVICE_FULL_NAME, health_pb2.HealthCheckResponse.NOT_SERVING)
    health_servicer.set(PRESENCE_SERVICE_FULL_NAME, health_pb2.HealthCheckResponse.NOT_SERVING)
    health_servicer.set("", health_pb2.HealthCheckResponse.NOT_SERVING)
    inference_pb2_grpc.add_InferenceServiceServicer_to_server(
        InferenceServicer(detector=detector, executor=executor, alert_client=alert_client),
        server,
    )
    presence_servicer = PresenceServicer()
    presence_pb2_grpc.add_PresenceServiceServicer_to_server(presence_servicer, server)
    register_presence_gauge(presence_servicer)
    bind_address = f"{settings.GRPC_HOST}:{settings.GRPC_PORT}"
    server.add_secure_port(bind_address, _server_credentials())
    log.info("loading detector")
    await asyncio.get_running_loop().run_in_executor(executor, detector.load)
    log.info("detector ready")
    await server.start()
    node_stats_task = asyncio.create_task(node_stats.run())
    health_servicer.set(INFERENCE_SERVICE_FULL_NAME, health_pb2.HealthCheckResponse.SERVING)
    health_servicer.set(PRESENCE_SERVICE_FULL_NAME, health_pb2.HealthCheckResponse.SERVING)
    health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)
    log.info("grpc server listening on %s", bind_address)
    stop_event = asyncio.Event()

    def _on_signal(signame: str) -> None:
        log.info("received %s, initiating graceful shutdown", signame)
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _on_signal, sig.name)
    await stop_event.wait()
    health_servicer.set(INFERENCE_SERVICE_FULL_NAME, health_pb2.HealthCheckResponse.NOT_SERVING)
    health_servicer.set(PRESENCE_SERVICE_FULL_NAME, health_pb2.HealthCheckResponse.NOT_SERVING)
    health_servicer.set("", health_pb2.HealthCheckResponse.NOT_SERVING)
    await node_stats.stop()
    node_stats_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await node_stats_task
    await server.stop(grace=5)
    executor.shutdown(wait=True)
    detector.close()
    alert_client.close()
    log.info("ai service stopped")


def main() -> None:
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
