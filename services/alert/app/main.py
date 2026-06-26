from __future__ import annotations

import asyncio
import logging
import signal

import grpc
import uvicorn
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

from app.core.config import settings
from app.grpc_gen import alert_pb2_grpc
from app.http_app import create_app
from app.observability import setup_observability
from app.servicer import AlertServicer

ALERT_SERVICE_FULL_NAME = "theftdetection.v1.AlertService"


class AsyncHealthServicer(health.HealthServicer):
    async def Check(self, request, context):
        return super().Check(request, context)

    async def Watch(self, request, context):
        async for response in self._async_watch(request, context):
            yield response

    async def _async_watch(self, request, context):
        for response in super().Watch(request, context):
            yield response


async def _run_grpc(stop_event: asyncio.Event, log: logging.Logger) -> None:
    server = grpc.aio.server()

    health_servicer = AsyncHealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    health_servicer.set(ALERT_SERVICE_FULL_NAME, health_pb2.HealthCheckResponse.NOT_SERVING)
    health_servicer.set("", health_pb2.HealthCheckResponse.NOT_SERVING)

    alert_pb2_grpc.add_AlertServiceServicer_to_server(AlertServicer(), server)

    bind_address = f"{settings.GRPC_HOST}:{settings.GRPC_PORT}"
    server.add_insecure_port(bind_address)

    await server.start()
    health_servicer.set(ALERT_SERVICE_FULL_NAME, health_pb2.HealthCheckResponse.SERVING)
    health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)
    log.info("grpc server listening on %s", bind_address)

    await stop_event.wait()

    health_servicer.set(ALERT_SERVICE_FULL_NAME, health_pb2.HealthCheckResponse.NOT_SERVING)
    health_servicer.set("", health_pb2.HealthCheckResponse.NOT_SERVING)
    await server.stop(grace=5)
    log.info("grpc server stopped")


async def _run_http(stop_event: asyncio.Event, log: logging.Logger) -> None:
    config = uvicorn.Config(
        app=create_app(),
        host=settings.HTTP_HOST,
        port=settings.HTTP_PORT,
        log_level=settings.LOG_LEVEL.lower(),
        access_log=False,
        lifespan="off",
    )
    server = uvicorn.Server(config)
    log.info("http server listening on %s:%d", settings.HTTP_HOST, settings.HTTP_PORT)

    serve_task = asyncio.create_task(server.serve())
    await stop_event.wait()

    server.should_exit = True
    await serve_task
    log.info("http server stopped")


async def _serve() -> None:
    setup_observability(service_name="theft-alert")
    logging.getLogger().setLevel(settings.LOG_LEVEL)
    log = logging.getLogger("app.main")

    log.info("starting alert service")

    stop_event = asyncio.Event()

    def _on_signal(signame: str) -> None:
        log.info("received %s, initiating graceful shutdown", signame)
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _on_signal, sig.name)

    await asyncio.gather(
        _run_grpc(stop_event, log),
        _run_http(stop_event, log),
    )

    log.info("alert service stopped")


def main() -> None:
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
