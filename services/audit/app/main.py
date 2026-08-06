from __future__ import annotations

import asyncio
import contextlib
import logging
import signal

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from grpc_reflection.v1alpha import reflection
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import dispose_engine, get_sessionmaker
from app.core.redis import close_redis, get_redis
from app.server.grpc_gen import audit_pb2, audit_pb2_grpc
from app.server.servicer import AuditServicer

AUDIT_SERVICE_FULL_NAME = "theftdetection.v1.AuditService"

logger = logging.getLogger(__name__)


class AsyncHealthServicer(health.HealthServicer):
    async def Check(self, request, context):
        return super().Check(request, context)

    async def Watch(self, request, context):
        for response in super().Watch(request, context):
            yield response


async def _postgres_reachable(timeout: float) -> bool:
    factory = get_sessionmaker()
    try:
        async with asyncio.timeout(timeout):
            async with factory() as session:
                await session.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.warning("postgres probe failed", exc_info=True)
        return False


async def _redis_reachable(timeout: float) -> bool:
    try:
        async with asyncio.timeout(timeout):
            await get_redis().ping()
        return True
    except Exception:
        logger.warning("redis probe failed", exc_info=True)
        return False


async def _probe_dependencies(timeout: float) -> bool:
    postgres_ok, redis_ok = await asyncio.gather(
        _postgres_reachable(timeout),
        _redis_reachable(timeout),
    )
    return postgres_ok and redis_ok


async def _watch_health(
    health_servicer: AsyncHealthServicer, stop_event: asyncio.Event
) -> None:
    settings = get_settings()
    previous: int | None = None
    while not stop_event.is_set():
        healthy = await _probe_dependencies(settings.health_probe_timeout_seconds)
        status = (
            health_pb2.HealthCheckResponse.SERVING
            if healthy
            else health_pb2.HealthCheckResponse.NOT_SERVING
        )
        if status != previous:
            logger.info(
                "health status %s",
                health_pb2.HealthCheckResponse.ServingStatus.Name(status).lower(),
            )
            health_servicer.set(AUDIT_SERVICE_FULL_NAME, status)
            health_servicer.set("", status)
            previous = status
        try:
            async with asyncio.timeout(settings.health_probe_interval_seconds):
                await stop_event.wait()
        except TimeoutError:
            continue


async def _run_grpc(stop_event: asyncio.Event) -> None:
    settings = get_settings()
    server = grpc.aio.server(
        migration_thread_pool=None,
        maximum_concurrent_rpcs=settings.grpc_max_concurrent_rpcs,
    )

    health_servicer = AsyncHealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    health_servicer.set(
        AUDIT_SERVICE_FULL_NAME, health_pb2.HealthCheckResponse.NOT_SERVING
    )
    health_servicer.set("", health_pb2.HealthCheckResponse.NOT_SERVING)

    audit_pb2_grpc.add_AuditServiceServicer_to_server(AuditServicer(), server)

    service_names = (
        audit_pb2.DESCRIPTOR.services_by_name["AuditService"].full_name,
        health.SERVICE_NAME,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(service_names, server)

    bind_address = f"{settings.grpc_host}:{settings.grpc_port}"
    server.add_insecure_port(bind_address)
    await server.start()
    logger.info("grpc server listening on %s", bind_address)

    health_task = asyncio.create_task(_watch_health(health_servicer, stop_event))
    try:
        await stop_event.wait()
    finally:
        health_servicer.set(
            AUDIT_SERVICE_FULL_NAME, health_pb2.HealthCheckResponse.NOT_SERVING
        )
        health_servicer.set("", health_pb2.HealthCheckResponse.NOT_SERVING)
        health_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await health_task
        await server.stop(grace=5)
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
        await _run_grpc(stop_event)
    finally:
        await close_redis()
        await dispose_engine()
    logger.info("audit server stopped")


def main() -> None:
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
