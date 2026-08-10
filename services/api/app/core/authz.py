from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from enum import StrEnum
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from starlette.requests import HTTPConnection

from app.grpc_gen import audit_pb2
from app.schemas.identity import CurrentUser
from app.services.audit_service import AuditClient
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


class TokenMissingError(Exception):
    pass


class TokenRejectedError(Exception):
    pass


def get_auth_client(request: Request) -> AuthClient:
    return AuthClient(request.app.state.auth_stub)


def build_auth_client(connection: HTTPConnection) -> AuthClient:
    return AuthClient(connection.app.state.auth_stub)


def extract_token(connection: HTTPConnection) -> str:
    from app.core.config import settings

    cookie_token = connection.cookies.get(settings.ACCESS_COOKIE_NAME)
    if cookie_token:
        return cookie_token
    header = connection.headers.get("authorization")
    if header is None:
        raise TokenMissingError
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise TokenMissingError
    return token


async def verify_connection(
    connection: HTTPConnection,
    auth_client: AuthClient,
    token: str,
) -> CurrentUser:
    source_ip = connection.client.host if connection.client else ""
    user_agent = connection.headers.get("user-agent", "")
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
        raise TokenRejectedError
    return CurrentUser(
        user_id=result.user_id,
        username=result.username,
        roles=result.roles,
        session_id=result.session_id,
    )


async def get_current_user(
    request: Request,
    auth_client: AuthClient = Depends(get_auth_client),
) -> CurrentUser:
    try:
        token = extract_token(request)
        return await verify_connection(request, auth_client, token)
    except (TokenMissingError, TokenRejectedError) as exc:
        raise _UNAUTHENTICATED from exc


def _resolve_permissions(roles: frozenset[str]) -> frozenset[Permission]:
    granted: set[Permission] = set()
    for role in roles:
        granted |= ROLE_PERMISSIONS.get(role, frozenset())
    return frozenset(granted)


def require_permission(
    permission: Permission,
) -> Callable[[CurrentUser], Coroutine[Any, Any, CurrentUser]]:
    async def _guard(
        request: Request,
        user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        granted = _resolve_permissions(user.roles)
        if permission not in granted:
            audit = AuditClient(request.app.state.audit_stub)
            audit.emit_authorization_denied(
                subject_id=user.user_id,
                required_permission=permission.value,
                channel=audit_pb2.AUTHORIZATION_CHANNEL_HTTP,
                method=request.method,
                path=request.url.path,
                roles=user.roles,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="insufficient permission",
            )
        return user

    return _guard
