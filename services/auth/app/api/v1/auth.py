from fastapi import APIRouter, status

from app.schemas.auth import (
    LoginRequest,
    LogoutResponse,
    RefreshRequest,
    TokenResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_STUB_ACCESS_TOKEN = "stub-access-token"
_STUB_REFRESH_TOKEN = "stub-refresh-token"
_STUB_EXPIRES_IN = 900


@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def login(payload: LoginRequest) -> TokenResponse:
    return TokenResponse(
        access_token=_STUB_ACCESS_TOKEN,
        refresh_token=_STUB_REFRESH_TOKEN,
        expires_in=_STUB_EXPIRES_IN,
    )


@router.post("/refresh", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def refresh(payload: RefreshRequest) -> TokenResponse:
    return TokenResponse(
        access_token=_STUB_ACCESS_TOKEN,
        refresh_token=_STUB_REFRESH_TOKEN,
        expires_in=_STUB_EXPIRES_IN,
    )


@router.post("/logout", response_model=LogoutResponse, status_code=status.HTTP_200_OK)
async def logout() -> LogoutResponse:
    return LogoutResponse(revoked=True)
