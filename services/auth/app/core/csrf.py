from __future__ import annotations

import secrets

from fastapi import HTTPException, status
from starlette.requests import Request

from app.core.config import get_settings


async def csrf_protect(request: Request) -> None:
    settings = get_settings()
    cookie_value = request.cookies.get(settings.csrf_cookie_name)
    header_value = request.headers.get(settings.csrf_header_name)
    if not cookie_value or not header_value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="csrf token missing",
        )
    if not secrets.compare_digest(cookie_value, header_value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="csrf token mismatch",
        )
