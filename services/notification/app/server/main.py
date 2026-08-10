from __future__ import annotations

import asyncio
import logging
import signal

import grpc
import uvicorn
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

from app.core.database import close_mongodb_connection, connect_to_mongodb
from app.server.grpc_gen import alert_pb2_grpc
from app.server.http_app import create_app
from app.server.interceptors import IdentityInterceptor
from app.server.observability import setup_server_observability
from app.server.servicer import AlertServicer
from app.shared.config import settings

ALERT_SERVICE_FULL_NAME = "theftdetection.v1.AlertService"


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


async def _run_grpc(stop_event: asyncio.Event, log: logging.Logger) -> None:
    server = grpc.aio.server(interceptors=[IdentityInterceptor()])
    health_servicer = AsyncHealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    health_servicer.set(ALERT_SERVICE_FULL_NAME, health_pb2.HealthCheckResponse.NOT_SERVING)
    health_servicer.set("", health_pb2.HealthCheckResponse.NOT_SERVING)
    alert_pb2_grpc.add_AlertServiceServicer_to_server(AlertServicer(), server)
    bind_address = f"{settings.GRPC_HOST}:{settings.GRPC_PORT}"
    server.add_secure_port(bind_address, _server_credentials())
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
    setup_server_observability()
    logging.getLogger().setLevel(settings.LOG_LEVEL)
    log = logging.getLogger("app.server.main")
    log.info("starting notification server")
    stop_event = asyncio.Event()

    def _on_signal(signame: str) -> None:
        log.info("received %s, initiating graceful shutdown", signame)
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _on_signal, sig.name)
    await connect_to_mongodb()
    try:
        await asyncio.gather(
            _run_grpc(stop_event, log),
            _run_http(stop_event, log),
        )
    finally:
        await close_mongodb_connection()
    log.info("notification server stopped")


def main() -> None:
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
