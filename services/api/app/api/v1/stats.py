from fastapi import APIRouter, Depends

from app.core.authz import Permission, require_permission
from app.dependencies import get_stats_usecase
from app.schemas.stats import StatsResponse
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
