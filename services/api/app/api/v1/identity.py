from fastapi import APIRouter, Depends

from app.core.authz import get_current_user, resolve_permissions
from app.schemas.identity import CurrentUser, IdentityResponse

router = APIRouter(prefix="/me", tags=["identity"])


@router.get("", response_model=IdentityResponse)
async def read_identity(
    user: CurrentUser = Depends(get_current_user),
) -> IdentityResponse:
    return IdentityResponse(
        user_id=user.user_id,
        username=user.username,
        roles=sorted(user.roles),
        permissions=sorted(permission.value for permission in resolve_permissions(user.roles)),
    )
