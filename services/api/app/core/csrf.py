from __future__ import annotations

import secrets

from fastapi import HTTPException, Request, status

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


async def csrf_protect(request: Request) -> None:
    from app.core.config import settings

    if request.method in _SAFE_METHODS:
        return
    if settings.ACCESS_COOKIE_NAME not in request.cookies:
        return
    cookie_value = request.cookies.get(settings.CSRF_COOKIE_NAME)
    header_value = request.headers.get(settings.CSRF_HEADER_NAME)
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
