from __future__ import annotations

import secrets

from fastapi import HTTPException, status
from starlette.requests import HTTPConnection

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


async def csrf_protect(connection: HTTPConnection) -> None:
    from app.core.config import settings

    if connection.scope["type"] != "http":
        return
    if connection.scope["method"] in _SAFE_METHODS:
        return
    cookie_value = connection.cookies.get(settings.CSRF_COOKIE_NAME)
    header_value = connection.headers.get(settings.CSRF_HEADER_NAME)
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
