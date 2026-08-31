from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.core.config import get_settings
from app.core.csrf import csrf_protect

_FORBIDDEN = 403


def _request(cookie: str | None = None, header: str | None = None) -> Request:
    settings = get_settings()
    headers: list[tuple[bytes, bytes]] = []
    if cookie is not None:
        raw = f"{settings.csrf_cookie_name}={cookie}"
        headers.append((b"cookie", raw.encode("latin-1")))
    if header is not None:
        headers.append(
            (settings.csrf_header_name.lower().encode("latin-1"), header.encode("latin-1"))
        )
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/auth/refresh",
            "headers": headers,
        }
    )


async def test_matching_cookie_and_header_passes():
    assert await csrf_protect(_request(cookie="token-value", header="token-value")) is None


async def test_missing_cookie_is_rejected():
    with pytest.raises(HTTPException) as excinfo:
        await csrf_protect(_request(header="token-value"))

    assert excinfo.value.status_code == _FORBIDDEN
    assert excinfo.value.detail == "csrf token missing"


async def test_missing_header_is_rejected():
    with pytest.raises(HTTPException) as excinfo:
        await csrf_protect(_request(cookie="token-value"))

    assert excinfo.value.status_code == _FORBIDDEN
    assert excinfo.value.detail == "csrf token missing"


async def test_both_missing_is_rejected():
    with pytest.raises(HTTPException) as excinfo:
        await csrf_protect(_request())

    assert excinfo.value.detail == "csrf token missing"


async def test_empty_cookie_value_is_rejected():
    with pytest.raises(HTTPException) as excinfo:
        await csrf_protect(_request(cookie="", header="token-value"))

    assert excinfo.value.detail == "csrf token missing"


async def test_empty_header_value_is_rejected():
    with pytest.raises(HTTPException) as excinfo:
        await csrf_protect(_request(cookie="token-value", header=""))

    assert excinfo.value.detail == "csrf token missing"


async def test_mismatched_values_are_rejected():
    with pytest.raises(HTTPException) as excinfo:
        await csrf_protect(_request(cookie="token-value", header="other-value"))

    assert excinfo.value.status_code == _FORBIDDEN
    assert excinfo.value.detail == "csrf token mismatch"


async def test_comparison_is_case_sensitive():
    with pytest.raises(HTTPException) as excinfo:
        await csrf_protect(_request(cookie="Token-Value", header="token-value"))

    assert excinfo.value.detail == "csrf token mismatch"


async def test_prefix_of_valid_token_is_rejected():
    with pytest.raises(HTTPException) as excinfo:
        await csrf_protect(_request(cookie="token-value", header="token"))

    assert excinfo.value.detail == "csrf token mismatch"


async def test_configured_header_name_resolves_against_lowercase_wire_name():
    settings = get_settings()
    assert settings.csrf_header_name != settings.csrf_header_name.lower()

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/auth/refresh",
            "headers": [
                (b"cookie", f"{settings.csrf_cookie_name}=token-value".encode("latin-1")),
                (settings.csrf_header_name.lower().encode(), b"token-value"),
            ],
        }
    )

    assert await csrf_protect(request) is None


async def test_non_ascii_cookie_value_is_rejected_without_error():
    with pytest.raises(HTTPException) as excinfo:
        await csrf_protect(_request(cookie="tökén-value", header="token-value"))

    assert excinfo.value.status_code == _FORBIDDEN
    assert excinfo.value.detail == "csrf token mismatch"


async def test_non_ascii_header_value_is_rejected_without_error():
    with pytest.raises(HTTPException) as excinfo:
        await csrf_protect(_request(cookie="token-value", header="tökén-value"))

    assert excinfo.value.status_code == _FORBIDDEN
    assert excinfo.value.detail == "csrf token mismatch"


async def test_matching_non_ascii_values_pass():
    assert await csrf_protect(_request(cookie="tökén-value", header="tökén-value")) is None
