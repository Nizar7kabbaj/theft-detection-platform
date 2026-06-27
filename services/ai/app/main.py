from __future__ import annotations

import asyncio
import logging
import signal
from concurrent.futures import ThreadPoolExecutor

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

from app.core.config import settings
from app.grpc_gen import inference_pb2_grpc
from app.inference import LSTMDetector
from app.observability import setup_observability
from app.servicer import InferenceServicer

INFERENCE_SERVICE_FULL_NAME = "theftdetection.v1.InferenceService"


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
        lstm_model_path=settings.LSTM_MODEL_PATH,
        device=settings.DEVICE,
        anomaly_threshold=settings.ANOMALY_THRESHOLD,
        person_class=settings.YOLO_PERSON_CLASS,
    )

    server = grpc.aio.server()

    health_servicer = AsyncHealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    health_servicer.set(INFERENCE_SERVICE_FULL_NAME, health_pb2.HealthCheckResponse.NOT_SERVING)
    health_servicer.set("", health_pb2.HealthCheckResponse.NOT_SERVING)

    inference_pb2_grpc.add_InferenceServiceServicer_to_server(
        InferenceServicer(detector=detector, executor=executor),
        server,
    )

    bind_address = f"{settings.GRPC_HOST}:{settings.GRPC_PORT}"
    server.add_insecure_port(bind_address)

    log.info("loading detector")
    await asyncio.get_running_loop().run_in_executor(executor, detector.load)
    log.info("detector ready")

    await server.start()
    health_servicer.set(INFERENCE_SERVICE_FULL_NAME, health_pb2.HealthCheckResponse.SERVING)
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
    health_servicer.set("", health_pb2.HealthCheckResponse.NOT_SERVING)
    await server.stop(grace=5)
    executor.shutdown(wait=True)
    log.info("ai service stopped")


def main() -> None:
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
