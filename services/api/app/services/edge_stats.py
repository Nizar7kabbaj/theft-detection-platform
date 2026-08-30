from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EdgeStats:
    average_fps: float | None
    latency_ms: float | None
    gpu_temperature_c: int | None
    gpu_name: str | None
    reporting_cameras: int


def _decode(raw: object) -> dict[str, object] | None:
    if isinstance(raw, Exception) or raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "ignore")
    if not isinstance(raw, str):
        return None
    try:
        parsed = json.loads(raw)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _number(payload: dict[str, object], field: str) -> float | None:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


async def read_edge_stats(stream: Redis, camera_ids: list[str]) -> EdgeStats:
    keys = [f"{settings.STREAM_STATS_CAMERA_PREFIX}:{camera_id}" for camera_id in camera_ids]
    keys.append(settings.STREAM_STATS_NODE_KEY)
    pipe = stream.pipeline(transaction=False)
    for key in keys:
        pipe.get(key)
    try:
        replies = await pipe.execute(raise_on_error=False)
    except RedisError as exc:
        logger.warning("edge stats read failed count=%d: %s", len(keys), exc)
        return EdgeStats(None, None, None, None, 0)

    node = _decode(replies[-1])
    fps_values: list[float] = []
    latency_values: list[float] = []
    for reply in replies[:-1]:
        payload = _decode(reply)
        if payload is None:
            continue
        fps = _number(payload, "fps")
        if fps is not None:
            fps_values.append(fps)
        latency = _number(payload, "latency_ms")
        if latency is not None:
            latency_values.append(latency)

    average_fps = round(sum(fps_values) / len(fps_values), 1) if fps_values else None
    latency_ms = round(sum(latency_values) / len(latency_values), 1) if latency_values else None

    temperature: int | None = None
    gpu_name: str | None = None
    if node is not None:
        raw_temperature = _number(node, "gpu_temperature_c")
        temperature = None if raw_temperature is None else int(raw_temperature)
        name = node.get("gpu_name")
        gpu_name = name if isinstance(name, str) else None

    return EdgeStats(average_fps, latency_ms, temperature, gpu_name, len(fps_values))
