from fastapi import APIRouter, Depends

from app.core.authz import Permission, require_permission
from app.dependencies import get_policy_usecase
from app.schemas.identity import CurrentUser
from app.schemas.policy import PolicyResponse, PolicyRevision, PolicyUpdate
from app.usecases.policy_usecase import PolicyUseCase

router = APIRouter(prefix="/policy/detection", tags=["policy"])


@router.get(
    "",
    response_model=PolicyResponse,
    dependencies=[Depends(require_permission(Permission.SETTINGS_READ))],
)
async def read_policy(
    usecase: PolicyUseCase = Depends(get_policy_usecase),
) -> PolicyResponse:
    return await usecase.current()


@router.get(
    "/history",
    response_model=list[PolicyRevision],
    dependencies=[Depends(require_permission(Permission.SETTINGS_READ))],
)
async def read_policy_history(
    usecase: PolicyUseCase = Depends(get_policy_usecase),
) -> list[PolicyRevision]:
    return await usecase.history()


@router.put(
    "",
    response_model=PolicyResponse,
)
async def update_policy(
    payload: PolicyUpdate,
    usecase: PolicyUseCase = Depends(get_policy_usecase),
    user: CurrentUser = Depends(require_permission(Permission.SETTINGS_WRITE)),
) -> PolicyResponse:
    return await usecase.update(
        expected_version=payload.expected_version,
        policy=payload.policy,
        actor_user_id=user.user_id,
    )
