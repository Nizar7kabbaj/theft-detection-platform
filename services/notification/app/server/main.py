from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
from collections.abc import Mapping

import grpc
import uvicorn
from grpc_health.v1 import health_pb2_grpc
from redis.asyncio import Redis, from_url

from app.core.database import close_mongodb_connection, connect_to_mongodb, ping_mongodb
from app.server.grpc_gen import alert_pb2_grpc
from app.server.health import HealthState, Probe, start_probe_server
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


def _broker_client() -> Redis:
    tls: dict[str, str] = (
        {
            "ssl_cert_reqs": "required",
            "ssl_ca_certs": str(settings.TLS_CA_FILE),
            "ssl_certfile": str(settings.TLS_CERT_FILE),
            "ssl_keyfile": str(settings.TLS_KEY_FILE),
        }
        if settings.REDIS_TLS
        else {}
    )
    return from_url(settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1, **tls)


def _http_started(server: uvicorn.Server) -> Probe:
    async def probe() -> bool:
        return server.started

    return probe


async def _run_grpc(
    stop_event: asyncio.Event, probes: Mapping[str, Probe], log: logging.Logger
) -> None:
    state = HealthState(readiness_names=(ALERT_SERVICE_FULL_NAME,))
    await state.start()
    probe_server = await start_probe_server(
        state.servicer, settings.HEALTH_HOST, settings.HEALTH_PORT
    )
    watch_task = asyncio.create_task(
        state.watch(
            probes,
            settings.HEALTH_PROBE_INTERVAL_SEC,
            settings.HEALTH_PROBE_TIMEOUT_SEC,
            stop_event,
        )
    )
    server = grpc.aio.server(interceptors=[IdentityInterceptor()])
    health_pb2_grpc.add_HealthServicer_to_server(state.servicer, server)
    alert_pb2_grpc.add_AlertServiceServicer_to_server(AlertServicer(), server)
    bind_address = f"{settings.GRPC_HOST}:{settings.GRPC_PORT}"
    server.add_secure_port(bind_address, _server_credentials())
    try:
        await server.start()
        log.info("grpc server listening on %s", bind_address)
        await stop_event.wait()
    finally:
        watch_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await watch_task
        await state.shutdown()
        await server.stop(grace=5)
        await probe_server.stop(grace=None)
        log.info("grpc server stopped")


def _build_http_server() -> uvicorn.Server:
    config = uvicorn.Config(
        app=create_app(),
        host=settings.HTTP_HOST,
        port=settings.HTTP_PORT,
        log_level=settings.LOG_LEVEL.lower(),
        access_log=False,
        lifespan="off",
    )
    return uvicorn.Server(config)


async def _run_http(stop_event: asyncio.Event, server: uvicorn.Server, log: logging.Logger) -> None:
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
    broker = _broker_client()
    http_server = _build_http_server()
    probes: dict[str, Probe] = {
        "mongodb": ping_mongodb,
        "broker": broker.ping,
        "http": _http_started(http_server),
    }
    try:
        await asyncio.gather(
            _run_grpc(stop_event, probes, log),
            _run_http(stop_event, http_server, log),
        )
    finally:
        await broker.aclose()
        await close_mongodb_connection()
    log.info("notification server stopped")


def main() -> None:
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
