from fastapi import APIRouter, Depends

from app.dependencies import get_stats_usecase
from app.schemas.stats import StatsResponse
from app.usecases.stats_usecase import StatsUseCase

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("", response_model=StatsResponse)
async def get_stats(
    usecase: StatsUseCase = Depends(get_stats_usecase),
) -> StatsResponse:
    return await usecase.overview()
