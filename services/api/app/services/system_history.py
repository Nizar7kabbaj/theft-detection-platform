from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.services.system_stats import (
    _CPU_QUERY,
    _CPU_TEMPERATURE_QUERY,
    _GPU_QUERY,
    _GPU_TEMPERATURE_QUERY,
    _MEMORY_QUERY,
    _NETWORK_QUERY,
)

logger = logging.getLogger(__name__)
_SAMPLE_PAIR_LENGTH = 2


@dataclass(frozen=True, slots=True)
class SystemHistory:
    cpu: list[float]
    gpu: list[float]
    memory: list[float]
    network: list[float]
    cpu_temperature: list[float]
    gpu_temperature: list[float]


def _empty() -> SystemHistory:
    return SystemHistory([], [], [], [], [], [])


def _series(payload: object) -> list[float]:
    if not isinstance(payload, dict) or payload.get("status") != "success":
        return []
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    result = data.get("result")
    if not isinstance(result, list) or not result:
        return []
    first = result[0]
    if not isinstance(first, dict):
        return []
    values = first.get("values")
    if not isinstance(values, list):
        return []
    points: list[float] = []
    for pair in values:
        if not isinstance(pair, list) or len(pair) != _SAMPLE_PAIR_LENGTH:
            continue
        try:
            number = float(str(pair[1]))
        except ValueError:
            continue
        if math.isnan(number) or math.isinf(number):
            continue
        points.append(round(number, 2))
    return points


async def _range(client: httpx.AsyncClient, expression: str, start: int, end: int) -> object | None:
    try:
        response = await client.post(
            "/api/v1/query_range",
            data={
                "query": expression,
                "start": str(start),
                "end": str(end),
                "step": str(settings.SYSTEM_HISTORY_STEP_SECONDS),
            },
        )
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("prometheus range query failed: %s", exc)
        return None


async def read_system_history(client: httpx.AsyncClient) -> SystemHistory:
    end = int(time.time())
    start = end - settings.SYSTEM_HISTORY_WINDOW_SECONDS
    cpu, gpu, memory, network, cpu_temperature, gpu_temperature = await asyncio.gather(
        _range(client, _CPU_QUERY, start, end),
        _range(client, _GPU_QUERY, start, end),
        _range(client, _MEMORY_QUERY, start, end),
        _range(client, _NETWORK_QUERY, start, end),
        _range(client, _CPU_TEMPERATURE_QUERY, start, end),
        _range(client, _GPU_TEMPERATURE_QUERY, start, end),
    )
    if cpu is None and gpu is None and memory is None and network is None:
        return _empty()
    return SystemHistory(
        cpu=_series(cpu),
        gpu=_series(gpu),
        memory=_series(memory),
        network=_series(network),
        cpu_temperature=_series(cpu_temperature),
        gpu_temperature=_series(gpu_temperature),
    )
