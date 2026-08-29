from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import FileResponse

from app.core.authz import Permission, require_permission
from app.core.idempotency import IdempotencyState, idempotency
from app.dependencies import get_alert_usecase
from app.schemas.alert import (
    AlertCreate,
    AlertDetail,
    AlertPage,
    AlertResponse,
    AlertSort,
    Decision,
    DecisionUpdate,
    Severity,
)
from app.schemas.identity import CurrentUser
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
    decision: Decision | None = Query(default=None),
    camera_id: str | None = Query(default=None, max_length=64),
    sort: AlertSort = Query(default=AlertSort.CREATED_AT),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None, max_length=256),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    usecase: AlertUseCase = Depends(get_alert_usecase),
) -> AlertPage:
    return await usecase.list(
        severity=severity,
        acknowledged=acknowledged,
        decision=decision,
        camera_id=camera_id,
        sort=sort,
        limit=limit,
        cursor=cursor,
        start=start,
        end=end,
    )


@router.get(
    "/cameras",
    response_model=list[str],
    dependencies=[Depends(require_permission(Permission.ALERT_READ))],
)
async def list_alert_cameras(
    usecase: AlertUseCase = Depends(get_alert_usecase),
) -> list[str]:
    return await usecase.camera_facet()


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
)
async def acknowledge_alert(
    alert_id: str,
    user: CurrentUser = Depends(require_permission(Permission.ALERT_ACKNOWLEDGE)),
    usecase: AlertUseCase = Depends(get_alert_usecase),
) -> AlertResponse:
    return await usecase.acknowledge(alert_id, user.user_id)


@router.patch(
    "/{alert_id}/decision",
    response_model=AlertDetail,
)
async def decide_alert(
    alert_id: str,
    payload: DecisionUpdate,
    user: CurrentUser = Depends(require_permission(Permission.ALERT_ACKNOWLEDGE)),
    usecase: AlertUseCase = Depends(get_alert_usecase),
) -> AlertDetail:
    return await usecase.decide(alert_id, payload.decision, user.user_id)
