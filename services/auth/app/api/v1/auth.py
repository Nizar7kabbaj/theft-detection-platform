from __future__ import annotations

from datetime import datetime, timezone
from ipaddress import ip_address

from fastapi import APIRouter, HTTPException, Request, Response, status

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
from app.core.redis import (
    check_login,
    record_failure,
    reset_failures,
    revoke_jti,
)
from app.core.config import get_settings
from app.core.cookies import (
    clear_auth_cookies,
    new_csrf_token,
    set_auth_cookies,
)
from app.repositories.user_repository import UserRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.schemas.auth import (
    LoginRequest,
    LogoutResponse,
    TokenResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_INVALID_CREDENTIALS = "invalid credentials"
_INVALID_REFRESH = "invalid refresh token"
_LOCKED_OUT = "too many failed login attempts"
_DUMMY_HASH = hash_password("timing-defense-dummy")


def _client_ip(request: Request) -> str:
    peer = request.client.host if request.client is not None else ""
    if not peer:
        return ""
    settings = get_settings()
    try:
        peer_addr = ip_address(peer)
    except ValueError:
        return peer
    if not any(peer_addr in net for net in settings.trusted_proxy_networks):
        return peer
    forwarded = request.headers.get("x-forwarded-for", "")
    if not forwarded:
        return peer
    hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
    for hop in reversed(hops):
        try:
            hop_addr = ip_address(hop)
        except ValueError:
            continue
        if any(hop_addr in net for net in settings.trusted_proxy_networks):
            continue
        return hop
    return peer


def _build_refresh_token(jti: str, secret: str) -> str:
    return f"{jti}.{secret}"


def _split_refresh_token(raw: str) -> tuple[str, str] | None:
    parts = raw.split(".", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    return parts[0], parts[1]


@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def login(
    payload: LoginRequest, request: Request, response: Response
) -> TokenResponse:
    settings = get_settings()
    ip = _client_ip(request)

    locked, retry_ms = await check_login(ip, payload.username)
    if locked:
        retry_after = (retry_ms + 999) // 1000
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=_LOCKED_OUT,
            headers={"Retry-After": str(retry_after)},
        )

    factory = get_sessionmaker()
    async with factory() as db:
        users = UserRepository(db)
        user = await users.get_by_username(payload.username)
        if user is None:
            verify_password(_DUMMY_HASH, payload.password)
            await record_failure(ip, payload.username)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=_INVALID_CREDENTIALS,
            )
        if not verify_password(user.password_hash, payload.password):
            await record_failure(ip, payload.username)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=_INVALID_CREDENTIALS,
            )
        sessions = SessionRepository(db)
        login_session = await sessions.create(
            user_id=user.id,
            source_ip=ip,
            user_agent=request.headers.get("user-agent", ""),
        )
        access_token, _, _ = sign_access_token(
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
        await reset_failures(ip, payload.username)
        set_auth_cookies(
            response=response,
            access_token=access_token,
            refresh_token=_build_refresh_token(root_jti, secret),
            csrf_token=new_csrf_token(),
            access_max_age=settings.access_token_ttl_seconds,
            refresh_max_age=settings.refresh_token_ttl_seconds,
        )
        return TokenResponse(expires_in=settings.access_token_ttl_seconds)


@router.post("/refresh", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def refresh(request: Request, response: Response) -> TokenResponse:
    settings = get_settings()
    raw = request.cookies.get(settings.refresh_cookie_name)
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_INVALID_REFRESH,
        )
    split = _split_refresh_token(raw)
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
        set_auth_cookies(
            response=response,
            access_token=access_token,
            refresh_token=_build_refresh_token(next_jti, next_secret),
            csrf_token=new_csrf_token(),
            access_max_age=settings.access_token_ttl_seconds,
            refresh_max_age=settings.refresh_token_ttl_seconds,
        )
        return TokenResponse(expires_in=settings.access_token_ttl_seconds)


@router.post("/logout", response_model=LogoutResponse, status_code=status.HTTP_200_OK)
async def logout(request: Request, response: Response) -> LogoutResponse:
    settings = get_settings()
    token = request.cookies.get(settings.access_cookie_name, "")
    if token:
        try:
            claims = decode_access_token(token)
        except TokenError:
            claims = None
        if claims is not None:
            jti = claims.get("jti")
            exp = claims.get("exp")
            if jti and exp:
                remaining = int(exp) - int(
                    datetime.now(timezone.utc).timestamp()
                )
                if remaining > 0:
                    await revoke_jti(jti, remaining)
    clear_auth_cookies(response)
    return LogoutResponse(revoked=True)
