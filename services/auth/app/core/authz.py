from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, Request, status
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.core.database import get_sessionmaker
from app.core.redis import is_token_revoked
from app.core.roles import Role
from app.core.tokens import TokenError, decode_access_token
from app.repositories.user_repository import UserRepository


@dataclass(frozen=True, slots=True)
class Actor:
    user_id: str
    username: str
    roles: frozenset[str]
    session_id: str


_NOT_AUTHENTICATED = "not authenticated"
_NOT_PERMITTED = "admin role required"


def _unauthenticated() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=_NOT_AUTHENTICATED,
    )


async def current_actor(request: Request) -> Actor:
    settings = get_settings()
    token = request.cookies.get(settings.access_cookie_name, "")
    if not token:
        raise _unauthenticated()
    try:
        claims = decode_access_token(token)
    except TokenError as exc:
        raise _unauthenticated() from exc
    jti = claims.get("jti", "")
    session_id = claims.get("sid", "")
    if not jti or not session_id:
        raise _unauthenticated()
    try:
        revoked = await is_token_revoked(jti, session_id)
    except RedisError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="revocation store unavailable",
        ) from exc
    if revoked:
        raise _unauthenticated()
    factory = get_sessionmaker()
    async with factory() as db:
        user = await UserRepository(db).get_by_id(claims.get("sub", ""))
    if user is None or not user.is_active:
        raise _unauthenticated()
    return Actor(
        user_id=user.id,
        username=user.username,
        roles=frozenset(user.roles),
        session_id=session_id,
    )


async def require_admin(request: Request) -> Actor:
    actor = await current_actor(request)
    if Role.ADMIN not in actor.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_NOT_PERMITTED,
        )
    return actor
