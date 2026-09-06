from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis

from app.core.authz import Permission, require_permission
from app.core.cache import get_or_set
from app.core.config import settings
from app.core.redis import get_redis
from app.dependencies import (
    get_camera_usecase,
    get_prometheus,
    get_stats_usecase,
    get_stream_redis,
)
from app.schemas.stats import (
    BucketUnit,
    EdgeStatsResponse,
    ServiceMemory,
    StatsResponse,
    StatsTimeseriesResponse,
    SystemHistoryResponse,
    SystemStatsResponse,
)
from app.services.edge_stats import read_edge_stats
from app.services.system_history import read_system_history
from app.services.system_stats import read_system_stats
from app.usecases.camera_usecase import CameraUseCase
from app.usecases.stats_usecase import StatsUseCase

router = APIRouter(prefix="/stats", tags=["stats"])

SYSTEM_CACHE_KEY = "cache:stats:system"
SYSTEM_HISTORY_CACHE_KEY = "cache:stats:system:history"


@router.get(
    "",
    response_model=StatsResponse,
    dependencies=[Depends(require_permission(Permission.STATS_READ))],
)
async def get_stats(
    usecase: StatsUseCase = Depends(get_stats_usecase),
) -> StatsResponse:
    return await usecase.overview()


@router.get(
    "/timeseries",
    response_model=StatsTimeseriesResponse,
    dependencies=[Depends(require_permission(Permission.STATS_READ))],
)
async def get_stats_timeseries(
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    unit: BucketUnit = Query(default=BucketUnit.HOUR),
    usecase: StatsUseCase = Depends(get_stats_usecase),
) -> StatsTimeseriesResponse:
    return await usecase.timeseries(start=start, end=end, unit=unit)


@router.get(
    "/system",
    response_model=SystemStatsResponse,
    dependencies=[Depends(require_permission(Permission.STATS_READ))],
)
async def get_system_stats(
    prometheus: httpx.AsyncClient = Depends(get_prometheus),
    redis: Redis = Depends(get_redis),
) -> SystemStatsResponse:
    async def loader() -> dict:
        stats = await read_system_stats(prometheus)
        return SystemStatsResponse(
            cpu_percent=stats.cpu_percent,
            memory_percent=stats.memory_percent,
            network_bytes_per_second=stats.network_bytes_per_second,
            gpu_percent=stats.gpu_percent,
            gpu_temperature_c=stats.gpu_temperature_c,
            cpu_temperature_c=stats.cpu_temperature_c,
            service_memory_bytes=ServiceMemory(**stats.service_memory_bytes),
        ).model_dump(mode="json")

    cached = await get_or_set(redis, SYSTEM_CACHE_KEY, settings.SYSTEM_STATS_TTL_SECONDS, loader)
    return SystemStatsResponse.model_validate(cached)


@router.get(
    "/system/history",
    response_model=SystemHistoryResponse,
    dependencies=[Depends(require_permission(Permission.STATS_READ))],
)
async def get_system_history(
    prometheus: httpx.AsyncClient = Depends(get_prometheus),
    redis: Redis = Depends(get_redis),
) -> SystemHistoryResponse:
    async def loader() -> dict:
        history = await read_system_history(prometheus)
        return SystemHistoryResponse(
            cpu=history.cpu,
            gpu=history.gpu,
            memory=history.memory,
            network=history.network,
            cpu_temperature=history.cpu_temperature,
            gpu_temperature=history.gpu_temperature,
        ).model_dump(mode="json")

    cached = await get_or_set(
        redis, SYSTEM_HISTORY_CACHE_KEY, settings.SYSTEM_HISTORY_TTL_SECONDS, loader
    )
    return SystemHistoryResponse.model_validate(cached)


@router.get(
    "/edge",
    response_model=EdgeStatsResponse,
    dependencies=[Depends(require_permission(Permission.STATS_READ))],
)
async def get_edge_stats(
    stream: Redis = Depends(get_stream_redis),
    cameras: CameraUseCase = Depends(get_camera_usecase),
) -> EdgeStatsResponse:
    registered = await cameras.list()
    camera_ids = [camera.camera_id for camera in registered]
    stats = await read_edge_stats(stream, camera_ids)
    return EdgeStatsResponse(
        average_fps=stats.average_fps,
        latency_ms=stats.latency_ms,
        gpu_temperature_c=stats.gpu_temperature_c,
        gpu_name=stats.gpu_name,
        reporting_cameras=stats.reporting_cameras,
        total_cameras=len(camera_ids),
    )
