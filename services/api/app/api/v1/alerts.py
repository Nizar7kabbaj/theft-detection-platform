from fastapi import APIRouter, Depends, Query, status

from app.core.authz import Permission, require_permission
from app.core.idempotency import IdempotencyState, idempotency
from app.dependencies import get_alert_usecase
from app.schemas.alert import AlertCreate, AlertResponse, Severity
from app.usecases.alert_usecase import AlertUseCase

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.post(
    "",
    response_model=AlertResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permission.ALERT_WRITE))],
)
async def create_alert(
    payload: AlertCreate,
    usecase: AlertUseCase = Depends(get_alert_usecase),
    idem: IdempotencyState = Depends(idempotency),
) -> AlertResponse:
    if idem.is_hit:
        return AlertResponse.model_validate(idem.cached_response)
    result = await usecase.create(payload)
    await idem.store(result.model_dump(mode="json", by_alias=True))
    return result


@router.get(
    "",
    response_model=list[AlertResponse],
    dependencies=[Depends(require_permission(Permission.ALERT_READ))],
)
async def list_alerts(
    severity: Severity | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    skip: int = Query(default=0, ge=0),
    usecase: AlertUseCase = Depends(get_alert_usecase),
) -> list[AlertResponse]:
    return await usecase.list(severity=severity, limit=limit, skip=skip)


@router.patch(
    "/{alert_id}/acknowledge",
    response_model=AlertResponse,
    dependencies=[Depends(require_permission(Permission.ALERT_ACKNOWLEDGE))],
)
async def acknowledge_alert(
    alert_id: str,
    usecase: AlertUseCase = Depends(get_alert_usecase),
) -> AlertResponse:
    return await usecase.acknowledge(alert_id)


@router.delete(
    "/{alert_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission(Permission.ALERT_WRITE))],
)
async def delete_alert(
    alert_id: str,
    usecase: AlertUseCase = Depends(get_alert_usecase),
) -> None:
    await usecase.delete(alert_id)
