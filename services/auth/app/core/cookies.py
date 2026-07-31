from __future__ import annotations

import secrets

from fastapi import Response

from app.core.config import get_settings


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
    csrf_token: str,
    access_max_age: int,
    refresh_max_age: int,
) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.access_cookie_name,
        value=access_token,
        max_age=access_max_age,
        httponly=True,
        secure=True,
        samesite=settings.cookie_samesite,
        path="/",
    )
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=refresh_token,
        max_age=refresh_max_age,
        httponly=True,
        secure=True,
        samesite=settings.cookie_samesite,
        path="/",
    )
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf_token,
        max_age=refresh_max_age,
        httponly=False,
        secure=True,
        samesite=settings.cookie_samesite,
        path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    settings = get_settings()
    for name in (
        settings.access_cookie_name,
        settings.refresh_cookie_name,
        settings.csrf_cookie_name,
    ):
        response.delete_cookie(
            key=name,
            secure=True,
            samesite=settings.cookie_samesite,
            path="/",
        )
