from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, status

from app.core.security import hash_password, verify_password
from app.core.tokens import (
    TokenError,
    decode_access_token,
    hash_refresh_secret,
    new_jti,
    new_refresh_secret,
    sign_access_token,
)
from app.core.database import get_sessionmaker
from app.core.redis import is_revoked, revoke_jti
from app.core.config import get_settings
from app.repositories.user_repository import UserRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.schemas.auth import (
    LoginRequest,
    LogoutResponse,
    RefreshRequest,
    TokenResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_INVALID_CREDENTIALS = "invalid credentials"
_INVALID_REFRESH = "invalid refresh token"
_DUMMY_HASH = hash_password("timing-defense-dummy")


def _client_ip(request: Request) -> str:
    if request.client is not None:
        return request.client.host
    return ""


def _build_refresh_token(jti: str, secret: str) -> str:
    return f"{jti}.{secret}"


def _split_refresh_token(raw: str) -> tuple[str, str] | None:
    parts = raw.split(".", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    return parts[0], parts[1]


@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def login(payload: LoginRequest, request: Request) -> TokenResponse:
    settings = get_settings()
    factory = get_sessionmaker()
    async with factory() as db:
        users = UserRepository(db)
        user = await users.get_by_username(payload.username)

        if user is None:
            verify_password(_DUMMY_HASH, payload.password)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=_INVALID_CREDENTIALS,
            )

        if not verify_password(user.password_hash, payload.password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=_INVALID_CREDENTIALS,
            )

        sessions = SessionRepository(db)
        login_session = await sessions.create(
            user_id=user.id,
            source_ip=_client_ip(request),
            user_agent=request.headers.get("user-agent", ""),
        )

        access_token, _, access_expires_at = sign_access_token(
            user_id=user.id,
            username=user.username,
            roles=user.roles,
            session_id=login_session.id,
        )

        root_jti = new_jti()
        secret = new_refresh_secret()
        now = datetime.now(timezone.utc)
        refresh_expires_at = datetime.fromtimestamp(
            now.timestamp() + settings.refresh_token_ttl_seconds,
            tz=timezone.utc,
        )

        refresh_tokens = RefreshTokenRepository(db)
        await refresh_tokens.create(
            jti=root_jti,
            family_id=root_jti,
            session_id=login_session.id,
            token_hash=hash_refresh_secret(secret),
            expires_at=refresh_expires_at,
        )

        await db.commit()

        return TokenResponse(
            access_token=access_token,
            refresh_token=_build_refresh_token(root_jti, secret),
            expires_in=settings.access_token_ttl_seconds,
        )


@router.post("/refresh", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def refresh(payload: RefreshRequest, request: Request) -> TokenResponse:
    settings = get_settings()
    split = _split_refresh_token(payload.refresh_token)
    if split is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_INVALID_REFRESH,
        )
    presented_jti, presented_secret = split

    factory = get_sessionmaker()
    async with factory() as db:
        refresh_tokens = RefreshTokenRepository(db)
        stored = await refresh_tokens.get_by_jti_and_hash(
            presented_jti, hash_refresh_secret(presented_secret)
        )

        if stored is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=_INVALID_REFRESH,
            )

        if stored.revoked:
            await refresh_tokens.revoke_family(stored.family_id)
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=_INVALID_REFRESH,
            )

        now = datetime.now(timezone.utc)
        if stored.expires_at <= now:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=_INVALID_REFRESH,
            )

        sessions = SessionRepository(db)
        login_session = await sessions.get_by_id(stored.session_id)
        if login_session is None or login_session.revoked:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=_INVALID_REFRESH,
            )

        users = UserRepository(db)
        user = await users.get_by_id(login_session.user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=_INVALID_REFRESH,
            )

        await refresh_tokens.mark_rotated(stored.jti)

        access_token, _, _ = sign_access_token(
            user_id=user.id,
            username=user.username,
            roles=user.roles,
            session_id=login_session.id,
        )

        next_jti = new_jti()
        next_secret = new_refresh_secret()
        next_expires_at = datetime.fromtimestamp(
            now.timestamp() + settings.refresh_token_ttl_seconds,
            tz=timezone.utc,
        )

        await refresh_tokens.create(
            jti=next_jti,
            family_id=stored.family_id,
            session_id=login_session.id,
            token_hash=hash_refresh_secret(next_secret),
            expires_at=next_expires_at,
            rotated_from=stored.jti,
        )

        await db.commit()

        return TokenResponse(
            access_token=access_token,
            refresh_token=_build_refresh_token(next_jti, next_secret),
            expires_in=settings.access_token_ttl_seconds,
        )


@router.post("/logout", response_model=LogoutResponse, status_code=status.HTTP_200_OK)
async def logout(request: Request) -> LogoutResponse:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return LogoutResponse(revoked=True)

    token = header[7:].strip()
    try:
        claims = decode_access_token(token)
    except TokenError:
        return LogoutResponse(revoked=True)

    jti = claims.get("jti")
    exp = claims.get("exp")
    if jti and exp:
        remaining = int(exp) - int(datetime.now(timezone.utc).timestamp())
        if remaining > 0:
            await revoke_jti(jti, remaining)

    return LogoutResponse(revoked=True)
