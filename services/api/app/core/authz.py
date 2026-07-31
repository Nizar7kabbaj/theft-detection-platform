from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from enum import StrEnum
from typing import Any

from fastapi import Depends, HTTPException, Request, status

from app.schemas.identity import CurrentUser
from app.services.auth_service import AuthClient

logger = logging.getLogger(__name__)


class Permission(StrEnum):
    CAMERA_READ = "camera:read"
    CAMERA_WRITE = "camera:write"
    DETECTION_READ = "detection:read"
    DETECTION_WRITE = "detection:write"
    DETECTION_INFER = "detection:infer"
    ALERT_READ = "alert:read"
    ALERT_WRITE = "alert:write"
    ALERT_ACKNOWLEDGE = "alert:acknowledge"
    STATS_READ = "stats:read"
    AUDIT_QUERY = "audit:query"


ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "admin": frozenset(Permission),
    "operator": frozenset(
        {
            Permission.CAMERA_READ,
            Permission.CAMERA_WRITE,
            Permission.DETECTION_READ,
            Permission.DETECTION_INFER,
            Permission.ALERT_READ,
            Permission.ALERT_WRITE,
            Permission.ALERT_ACKNOWLEDGE,
            Permission.STATS_READ,
        }
    ),
    "viewer": frozenset(
        {
            Permission.CAMERA_READ,
            Permission.DETECTION_READ,
            Permission.ALERT_READ,
            Permission.STATS_READ,
        }
    ),
    "ml_engineer": frozenset(
        {
            Permission.DETECTION_READ,
            Permission.DETECTION_INFER,
            Permission.STATS_READ,
        }
    ),
    "compliance": frozenset(
        {
            Permission.ALERT_READ,
            Permission.DETECTION_READ,
            Permission.AUDIT_QUERY,
        }
    ),
}


_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_auth_client(request: Request) -> AuthClient:
    return AuthClient(request.app.state.auth_stub)


def _extract_token(request: Request) -> str:
    from app.core.config import settings

    cookie_token = request.cookies.get(settings.ACCESS_COOKIE_NAME)
    if cookie_token:
        return cookie_token
    header = request.headers.get("authorization")
    if header is None:
        raise _UNAUTHENTICATED
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _UNAUTHENTICATED
    return token


async def get_current_user(
    request: Request,
    auth_client: AuthClient = Depends(get_auth_client),
) -> CurrentUser:
    token = _extract_token(request)
    source_ip = request.client.host if request.client else ""
    user_agent = request.headers.get("user-agent", "")
    result = await auth_client.verify_token(
        token=token,
        source_ip=source_ip,
        user_agent=user_agent,
    )
    if not result.is_valid:
        from app.grpc_gen import auth_pb2 as pb

        logger.info(
            "token rejected status=%s",
            pb.VerificationStatus.Name(result.status),
        )
        raise _UNAUTHENTICATED
    return CurrentUser(
        user_id=result.user_id,
        username=result.username,
        roles=result.roles,
        session_id=result.session_id,
    )


def _resolve_permissions(roles: frozenset[str]) -> frozenset[Permission]:
    granted: set[Permission] = set()
    for role in roles:
        granted |= ROLE_PERMISSIONS.get(role, frozenset())
    return frozenset(granted)


def require_permission(
    permission: Permission,
) -> Callable[[CurrentUser], Coroutine[Any, Any, CurrentUser]]:
    async def _guard(
        user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        granted = _resolve_permissions(user.roles)
        if permission not in granted:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="insufficient permission",
            )
        return user

    return _guard
