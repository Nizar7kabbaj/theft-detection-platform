from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)
_SAMPLE_PAIR_LENGTH = 2

_SERVICE_JOBS = {
    "camera": "camera",
    "gate": "detect-gate",
    "inference": "ai",
    "notification": "notification-service",
}

_CPU_QUERY = '(1 - avg(rate(node_cpu_seconds_total{mode="idle"}[2m]))) * 100'
_MEMORY_QUERY = "(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100"
_NETWORK_QUERY = (
    'sum(rate(node_network_receive_bytes_total{device=~"wl.*|en.*"}[2m]))'
    ' + sum(rate(node_network_transmit_bytes_total{device=~"wl.*|en.*"}[2m]))'
)
_GPU_QUERY = "avg(nvidia_smi_utilization_gpu_ratio) * 100"
_GPU_TEMPERATURE_QUERY = "avg(nvidia_smi_temperature_gpu)"
_CPU_TEMPERATURE_QUERY = (
    "max(node_hwmon_temp_celsius * on(chip, sensor) group_left(label)"
    ' node_hwmon_sensor_label{label=~"Tctl|Tdie|Package id 0"})'
)
_SERVICE_MEMORY_QUERY = (
    'process_resident_memory_bytes{job=~"camera|detect-gate|ai|notification-service"}'
)


@dataclass(frozen=True, slots=True)
class SystemStats:
    cpu_percent: float | None
    memory_percent: float | None
    network_bytes_per_second: float | None
    gpu_percent: float | None
    gpu_temperature_c: int | None
    cpu_temperature_c: int | None
    service_memory_bytes: dict[str, int | None]


def _empty() -> SystemStats:
    return SystemStats(None, None, None, None, None, None, dict.fromkeys(_SERVICE_JOBS))


def _samples(payload: object) -> list[dict[str, object]]:
    if not isinstance(payload, dict) or payload.get("status") != "success":
        return []
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    result = data.get("result")
    if not isinstance(result, list):
        return []
    return [item for item in result if isinstance(item, dict)]


def _value(sample: dict[str, object]) -> float | None:
    pair = sample.get("value")
    if not isinstance(pair, list) or len(pair) != _SAMPLE_PAIR_LENGTH:
        return None
    try:
        number = float(str(pair[1]))
    except ValueError:
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _scalar(payload: object) -> float | None:
    samples = _samples(payload)
    if not samples:
        return None
    return _value(samples[0])


def _job(sample: dict[str, object]) -> str | None:
    metric = sample.get("metric")
    if not isinstance(metric, dict):
        return None
    name = metric.get("job")
    return name if isinstance(name, str) else None


def _service_memory(payload: object) -> dict[str, int | None]:
    by_job: dict[str, int] = {}
    for sample in _samples(payload):
        job = _job(sample)
        value = _value(sample)
        if job is None or value is None:
            continue
        by_job[job] = int(value)
    return {key: by_job.get(job) for key, job in _SERVICE_JOBS.items()}


async def _query(client: httpx.AsyncClient, expression: str) -> object | None:
    try:
        response = await client.post("/api/v1/query", data={"query": expression})
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("prometheus query failed: %s", exc)
        return None


async def read_system_stats(client: httpx.AsyncClient) -> SystemStats:
    (
        cpu,
        memory,
        network,
        gpu,
        gpu_temperature,
        cpu_temperature,
        service_memory,
    ) = await asyncio.gather(
        _query(client, _CPU_QUERY),
        _query(client, _MEMORY_QUERY),
        _query(client, _NETWORK_QUERY),
        _query(client, _GPU_QUERY),
        _query(client, _GPU_TEMPERATURE_QUERY),
        _query(client, _CPU_TEMPERATURE_QUERY),
        _query(client, _SERVICE_MEMORY_QUERY),
    )
    if cpu is None and memory is None and service_memory is None:
        return _empty()
    gpu_celsius = _scalar(gpu_temperature)
    cpu_celsius = _scalar(cpu_temperature)
    return SystemStats(
        cpu_percent=_round(_scalar(cpu)),
        memory_percent=_round(_scalar(memory)),
        network_bytes_per_second=_round(_scalar(network)),
        gpu_percent=_round(_scalar(gpu)),
        gpu_temperature_c=None if gpu_celsius is None else int(gpu_celsius),
        cpu_temperature_c=None if cpu_celsius is None else int(cpu_celsius),
        service_memory_bytes=_service_memory(service_memory),
    )


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


def open_prometheus_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.PROMETHEUS_URL,
        timeout=httpx.Timeout(settings.PROMETHEUS_TIMEOUT_SECONDS),
        limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
    )
