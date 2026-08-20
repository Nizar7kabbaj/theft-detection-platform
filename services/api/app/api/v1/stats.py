from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.core.authz import Permission, require_permission
from app.dependencies import get_stats_usecase
from app.schemas.stats import BucketUnit, StatsResponse, StatsTimeseriesResponse
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
