from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable, Iterable, Mapping

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

LIVENESS = "liveness"
READINESS = "readiness"
SERVING = health_pb2.HealthCheckResponse.SERVING
NOT_SERVING = health_pb2.HealthCheckResponse.NOT_SERVING

Probe = Callable[[], Awaitable[object]]

logger = logging.getLogger(__name__)


class HealthState:
    def __init__(self, readiness_names: Iterable[str] = ()) -> None:
        self.servicer = health.aio.HealthServicer()
        self._readiness_names = (READINESS, "", *readiness_names)
        self._ready: bool | None = None

    async def start(self) -> None:
        await self.servicer.set(LIVENESS, SERVING)
        await self._set_ready(ready=False, failed=[])

    async def watch(
        self,
        probes: Mapping[str, Probe],
        interval: float,
        timeout: float,
        stop: asyncio.Event,
    ) -> None:
        while not stop.is_set():
            failed = await self._run(probes, timeout)
            await self._set_ready(ready=not failed, failed=failed)
            with contextlib.suppress(TimeoutError):
                async with asyncio.timeout(interval):
                    await stop.wait()

    async def shutdown(self) -> None:
        await self.servicer.enter_graceful_shutdown()

    async def _run(self, probes: Mapping[str, Probe], timeout: float) -> list[str]:
        names = list(probes)
        results = await asyncio.gather(
            *(asyncio.wait_for(probes[name](), timeout) for name in names),
            return_exceptions=True,
        )
        failed: list[str] = []
        for name, result in zip(names, results, strict=True):
            if isinstance(result, BaseException) or result is False:
                logger.debug("%s check failed: %s", name, result)
                failed.append(name)
        return failed

    async def _set_ready(self, ready: bool, failed: list[str]) -> None:
        status = SERVING if ready else NOT_SERVING
        for name in self._readiness_names:
            await self.servicer.set(name, status)
        if ready == self._ready:
            return
        self._ready = ready
        if ready:
            logger.info("ready")
        elif failed:
            logger.warning("not ready, failing: %s", ", ".join(failed))


async def start_probe_server(
    servicer: health.aio.HealthServicer, host: str, port: int
) -> grpc.aio.Server:
    server = grpc.aio.server(
        maximum_concurrent_rpcs=8,
        options=[("grpc.so_reuseport", 0)],
    )
    health_pb2_grpc.add_HealthServicer_to_server(servicer, server)
    server.add_insecure_port(f"{host}:{port}")
    await server.start()
    logger.info("health server listening on %s:%d", host, port)
    return server
