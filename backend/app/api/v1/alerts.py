from fastapi import APIRouter, Depends, Query, status

from app.dependencies import get_alert_usecase
from app.schemas.alert import AlertCreate, AlertResponse
from app.usecases.alert_usecase import AlertUseCase

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.post("", response_model=AlertResponse, status_code=status.HTTP_201_CREATED)
async def create_alert(
    payload: AlertCreate,
    usecase: AlertUseCase = Depends(get_alert_usecase),
) -> AlertResponse:
    return await usecase.create(payload)


@router.get("", response_model=list[AlertResponse])
async def list_alerts(
    severity: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    skip: int = Query(default=0, ge=0),
    usecase: AlertUseCase = Depends(get_alert_usecase),
) -> list[AlertResponse]:
    return await usecase.list(severity=severity, limit=limit, skip=skip)


@router.patch("/{alert_id}/acknowledge", response_model=AlertResponse)
async def acknowledge_alert(
    alert_id: str,
    usecase: AlertUseCase = Depends(get_alert_usecase),
) -> AlertResponse:
    return await usecase.acknowledge(alert_id)


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(
    alert_id: str,
    usecase: AlertUseCase = Depends(get_alert_usecase),
) -> None:
    await usecase.delete(alert_id)
