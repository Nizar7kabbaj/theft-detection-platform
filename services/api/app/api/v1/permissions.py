from fastapi import APIRouter, Depends

from app.core.authz import Permission, require_permission
from app.core.permissions import ROLE_PERMISSIONS
from app.schemas.permissions import RolePermissionMap

router = APIRouter(prefix="/permissions", tags=["permissions"])


@router.get(
    "/roles",
    response_model=RolePermissionMap,
    dependencies=[Depends(require_permission(Permission.USER_READ))],
)
async def get_role_permissions() -> RolePermissionMap:
    return RolePermissionMap(
        permissions=sorted(str(permission) for permission in Permission),
        roles={
            role: sorted(str(permission) for permission in granted)
            for role, granted in ROLE_PERMISSIONS.items()
        },
    )
