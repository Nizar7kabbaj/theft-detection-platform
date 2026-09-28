from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
from collections.abc import Mapping

import grpc
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from grpc_health.v1 import health, health_pb2_grpc
from grpc_reflection.v1alpha import reflection
from sqlalchemy import text

from app.api.v1.auth import router as auth_router
from app.api.v1.users import router as users_router
from app.core.config import get_settings
from app.core.database import dispose_engine, get_sessionmaker
from app.core.redis import close_redis, get_redis
from app.server.grpc_gen import auth_pb2, auth_pb2_grpc
from app.server.health import HealthState, Probe, start_probe_server
from app.server.interceptors import IdentityInterceptor
from app.server.servicer import AuthServicer
from app.services.audit_drain import run_drain
from app.services.audit_service import close_audit_client, open_audit_client
from app.services.session_sweep import run_session_sweep

AUTH_SERVICE_FULL_NAME = "theftdetection.v1.AuthService"

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


def create_app() -> FastAPI:
    app = FastAPI(
        title="auth-service http",
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
    )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error in http handler: %s", exc)
        return JSONResponse(status_code=500, content={"detail": "internal error"})

    app.include_router(auth_router)
    app.include_router(users_router)
    return app


async def _postgres_ping() -> None:
    async with get_sessionmaker()() as session:
        await session.execute(text("SELECT 1"))


async def _redis_ping() -> None:
    await get_redis().ping()


def _http_started(server: uvicorn.Server) -> Probe:
    async def probe() -> bool:
        return server.started

    return probe


async def _run_grpc(stop_event: asyncio.Event, probes: Mapping[str, Probe]) -> None:
    settings = get_settings()
    state = HealthState(readiness_names=(AUTH_SERVICE_FULL_NAME,))
    await state.start()
    probe_server = await start_probe_server(
        state.servicer, settings.health_host, settings.health_port
    )
    watch_task = asyncio.create_task(
        state.watch(
            probes,
            settings.health_probe_interval_seconds,
            settings.health_probe_timeout_seconds,
            stop_event,
        )
    )
    server = grpc.aio.server(
        migration_thread_pool=None,
        maximum_concurrent_rpcs=None,
        interceptors=[IdentityInterceptor()],
    )
    health_pb2_grpc.add_HealthServicer_to_server(state.servicer, server)
    auth_pb2_grpc.add_AuthServiceServicer_to_server(AuthServicer(), server)
    reflection.enable_server_reflection(
        (
            auth_pb2.DESCRIPTOR.services_by_name["AuthService"].full_name,
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


def _build_http_server() -> uvicorn.Server:
    settings = get_settings()
    config = uvicorn.Config(
        app=create_app(),
        host=settings.http_host,
        port=settings.http_port,
        log_level=settings.log_level.lower(),
        access_log=False,
        lifespan="off",
    )
    return uvicorn.Server(config)


async def _run_http(stop_event: asyncio.Event, server: uvicorn.Server) -> None:
    settings = get_settings()
    logger.info("http server listening on %s:%d", settings.http_host, settings.http_port)
    serve_task = asyncio.create_task(server.serve())
    await stop_event.wait()
    server.should_exit = True
    await serve_task
    logger.info("http server stopped")


async def _serve() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())
    logger.info("starting auth server")
    open_audit_client()
    stop_event = asyncio.Event()

    def _on_signal(signame: str) -> None:
        logger.info("received %s, initiating graceful shutdown", signame)
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _on_signal, sig.name)

    http_server = _build_http_server()
    probes: dict[str, Probe] = {
        "postgres": _postgres_ping,
        "redis": _redis_ping,
        "http": _http_started(http_server),
    }
    grpc_task = asyncio.create_task(_run_grpc(stop_event, probes))
    http_task = asyncio.create_task(_run_http(stop_event, http_server))
    drain_task = asyncio.create_task(run_drain(stop_event))
    sweep_task = asyncio.create_task(run_session_sweep(stop_event))
    tasks = (grpc_task, http_task)
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        stop_event.set()
        for task in pending:
            await task
        for task in done:
            exc = task.exception()
            if exc is not None:
                logger.error("server task failed: %s", exc)
                raise exc
    finally:
        stop_event.set()
        await drain_task
        await sweep_task
        await close_redis()
        await dispose_engine()
        await close_audit_client()
    logger.info("auth server stopped")


def main() -> None:
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
