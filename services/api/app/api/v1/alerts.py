from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import FileResponse

from app.core.authz import Permission, require_permission
from app.core.idempotency import IdempotencyState, idempotency
from app.dependencies import get_alert_usecase
from app.schemas.alert import AlertCreate, AlertDetail, AlertPage, AlertResponse, Severity
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
    response_model=AlertPage,
    dependencies=[Depends(require_permission(Permission.ALERT_READ))],
)
async def list_alerts(
    severity: Severity | None = Query(default=None),
    acknowledged: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None, max_length=256),
    usecase: AlertUseCase = Depends(get_alert_usecase),
) -> AlertPage:
    return await usecase.list(
        severity=severity,
        acknowledged=acknowledged,
        limit=limit,
        cursor=cursor,
    )


@router.get(
    "/{alert_id}",
    response_model=AlertDetail,
    dependencies=[Depends(require_permission(Permission.ALERT_READ))],
)
async def get_alert(
    alert_id: str,
    usecase: AlertUseCase = Depends(get_alert_usecase),
) -> AlertDetail:
    return await usecase.get(alert_id)


@router.get(
    "/{alert_id}/snapshot",
    response_class=FileResponse,
    dependencies=[Depends(require_permission(Permission.ALERT_READ))],
)
async def get_alert_snapshot(
    alert_id: str,
    usecase: AlertUseCase = Depends(get_alert_usecase),
) -> FileResponse:
    path = await usecase.snapshot_path(alert_id)
    return FileResponse(
        path,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=300"},
    )


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
