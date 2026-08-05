from __future__ import annotations

import asyncio
import logging
import signal

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from grpc_reflection.v1alpha import reflection

from app.core.config import get_settings
from app.core.database import dispose_engine
from app.core.redis import close_redis
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


async def _run_grpc(stop_event: asyncio.Event) -> None:
    settings = get_settings()
    server = grpc.aio.server(
        migration_thread_pool=None,
        maximum_concurrent_rpcs=None,
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
    health_servicer.set(
        AUDIT_SERVICE_FULL_NAME, health_pb2.HealthCheckResponse.SERVING
    )
    health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)
    logger.info("grpc server listening on %s", bind_address)

    try:
        await stop_event.wait()
    finally:
        health_servicer.set(
            AUDIT_SERVICE_FULL_NAME, health_pb2.HealthCheckResponse.NOT_SERVING
        )
        health_servicer.set("", health_pb2.HealthCheckResponse.NOT_SERVING)
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
