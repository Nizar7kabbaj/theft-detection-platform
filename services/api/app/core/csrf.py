from __future__ import annotations

import secrets

from fastapi import HTTPException, status
from starlette.requests import HTTPConnection

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def _has_bearer_only(connection: HTTPConnection, access_cookie_name: str) -> bool:
    if connection.cookies.get(access_cookie_name):
        return False
    header = connection.headers.get("authorization")
    if header is None:
        return False
    scheme, _, token = header.partition(" ")
    return scheme.lower() == "bearer" and bool(token)


async def csrf_protect(connection: HTTPConnection) -> None:
    from app.core.config import settings

    if connection.scope["type"] != "http":
        return
    if connection.scope["method"] in _SAFE_METHODS:
        return
    if _has_bearer_only(connection, settings.ACCESS_COOKIE_NAME):
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
