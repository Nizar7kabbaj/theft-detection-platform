from datetime import datetime

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis

from app.core.authz import Permission, require_permission
from app.dependencies import get_camera_usecase, get_stats_usecase, get_stream_redis
from app.schemas.stats import (
    BucketUnit,
    EdgeStatsResponse,
    StatsResponse,
    StatsTimeseriesResponse,
)
from app.services.edge_stats import read_edge_stats
from app.usecases.camera_usecase import CameraUseCase
from app.usecases.stats_usecase import StatsUseCase

router = APIRouter(prefix="/stats", tags=["stats"])


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
