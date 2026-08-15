from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from starlette.requests import HTTPConnection

from app.core.database import get_database
from app.core.permissions import ROLE_PERMISSIONS, Permission, resolve_permissions
from app.grpc_gen import audit_pb2
from app.schemas.identity import CurrentUser
from app.services.audit_service import AuditClient
from app.services.auth_service import AuthClient

logger = logging.getLogger(__name__)

__all__ = [
    "ROLE_PERMISSIONS",
    "Permission",
    "TokenMissingError",
    "TokenRejectedError",
    "build_auth_client",
    "extract_token",
    "get_auth_client",
    "get_current_user",
    "require_permission",
    "resolve_permissions",
    "verify_connection",
]

_CODE_EXPIRED = "token_expired"
_CODE_SESSION_INVALID = "session_invalid"
_CODE_ACCOUNT_DISABLED = "account_disabled"


def _rejection_code(status_value: int) -> str:
    from app.grpc_gen import auth_pb2 as pb

    if status_value == pb.VerificationStatus.VERIFICATION_STATUS_EXPIRED:
        return _CODE_EXPIRED
    if status_value == pb.VerificationStatus.VERIFICATION_STATUS_USER_DISABLED:
        return _CODE_ACCOUNT_DISABLED
    return _CODE_SESSION_INVALID


def _unauthenticated(code: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"message": "not authenticated", "code": code},
        headers={"WWW-Authenticate": "Bearer"},
    )


class TokenMissingError(Exception):
    pass


class TokenRejectedError(Exception):
    def __init__(self, code: str = _CODE_SESSION_INVALID) -> None:
        super().__init__(code)
        self.code = code


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
        raise TokenRejectedError(_rejection_code(result.status))
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
    except TokenMissingError as exc:
        raise _unauthenticated(_CODE_SESSION_INVALID) from exc
    except TokenRejectedError as exc:
        raise _unauthenticated(exc.code) from exc


def require_permission(
    permission: Permission,
) -> Callable[[CurrentUser], Coroutine[Any, Any, CurrentUser]]:
    async def _guard(
        request: Request,
        user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        granted = resolve_permissions(user.roles)
        if permission not in granted:
            audit = AuditClient(get_database())
            await audit.emit_authorization_denied(
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


def require_ws_permission_unused() -> None:
    raise NotImplementedError
