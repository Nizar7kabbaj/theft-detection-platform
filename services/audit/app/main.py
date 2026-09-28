from __future__ import annotations

import asyncio
import contextlib
import logging
import signal

import grpc
from grpc_health.v1 import health, health_pb2_grpc
from grpc_reflection.v1alpha import reflection
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import dispose_engine, get_sessionmaker
from app.core.redis import close_redis, get_redis
from app.server.grpc_gen import audit_pb2, audit_pb2_grpc
from app.server.health import HealthState, start_probe_server
from app.server.interceptors import IdentityInterceptor
from app.server.servicer import AuditServicer

AUDIT_SERVICE_FULL_NAME = "theftdetection.v1.AuditService"

logger = logging.getLogger(__name__)


def _server_credentials() -> grpc.ServerCredentials:
    settings = get_settings()
    key = settings.tls_key_file.read_bytes()
    cert = settings.tls_cert_file.read_bytes()
    ca = settings.tls_ca_file.read_bytes()
    return grpc.ssl_server_credentials(
        [(key, cert)],
        root_certificates=ca,
        require_client_auth=settings.tls_require_client_auth,
    )


async def _postgres_ping() -> None:
    async with get_sessionmaker()() as session:
        await session.execute(text("SELECT 1"))


async def _redis_ping() -> None:
    await get_redis().ping()


async def _run(stop_event: asyncio.Event) -> None:
    settings = get_settings()
    state = HealthState(readiness_names=(AUDIT_SERVICE_FULL_NAME,))
    await state.start()
    probe_server = await start_probe_server(
        state.servicer, settings.health_host, settings.health_port
    )
    watch_task = asyncio.create_task(
        state.watch(
            {"postgres": _postgres_ping, "redis": _redis_ping},
            settings.health_probe_interval_seconds,
            settings.health_probe_timeout_seconds,
            stop_event,
        )
    )
    server = grpc.aio.server(
        migration_thread_pool=None,
        maximum_concurrent_rpcs=settings.grpc_max_concurrent_rpcs,
        interceptors=(IdentityInterceptor(),),
    )
    health_pb2_grpc.add_HealthServicer_to_server(state.servicer, server)
    audit_pb2_grpc.add_AuditServiceServicer_to_server(AuditServicer(), server)
    reflection.enable_server_reflection(
        (
            audit_pb2.DESCRIPTOR.services_by_name["AuditService"].full_name,
            health.SERVICE_NAME,
            reflection.SERVICE_NAME,
        ),
        server,
    )
    bind_address = f"{settings.grpc_host}:{settings.grpc_port}"
    server.add_secure_port(bind_address, _server_credentials())
    try:
        await server.start()
        logger.info("grpc server listening on %s", bind_address)
        await stop_event.wait()
    finally:
        watch_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await watch_task
        await state.shutdown()
        await server.stop(grace=5)
        await probe_server.stop(grace=None)
        logger.info("grpc server stopped")


async def _serve() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())
    logger.info("starting audit server")
    stop_event = asyncio.Event()

    def _on_signal(signame: str) -> None:
        logger.info("received %s, initiating graceful shutdown", signame)
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _on_signal, sig.name)

    try:
        await _run(stop_event)
    finally:
        await close_redis()
        await dispose_engine()
    logger.info("audit server stopped")


def main() -> None:
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
