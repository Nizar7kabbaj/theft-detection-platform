from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core import database as database_module
from app.core.config import get_settings
from app.core.security import hash_password
from app.core.tokens import decode_access_token
from app.main import create_app
from app.repositories.user_repository import UserRepository

_PASSWORD = "harness-password"
_USERNAME = "operator"
_DOMAIN = "testserver.local"
_OK = 200


@pytest.fixture(autouse=True)
async def app_resources(redis_client, db_session) -> AsyncIterator[None]:
    yield
    await database_module.dispose_engine()
    database_module._sessionmaker = None


@pytest.fixture
async def seeded_user(db_session):
    user = await UserRepository(db_session).create(
        username=_USERNAME, password_hash=hash_password(_PASSWORD), roles=["operator"]
    )
    await db_session.commit()
    return user


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="https://testserver") as http:
        yield http


def _headers(client: AsyncClient) -> dict[str, str]:
    settings = get_settings()
    return {settings.csrf_header_name: client.cookies[settings.csrf_cookie_name]}


async def _login(client: AsyncClient) -> None:
    await client.post("/auth/login", json={"username": _USERNAME, "password": _PASSWORD})


def _replace_access_cookie(client: AsyncClient, value: str) -> None:
    settings = get_settings()
    client.cookies.delete(settings.access_cookie_name)
    client.cookies.set(settings.access_cookie_name, value, domain=_DOMAIN, path="/")


async def test_logout_reports_revoked(client, seeded_user):
    await _login(client)
    response = await client.post("/auth/logout", headers=_headers(client))

    assert response.status_code == _OK
    assert response.json()["revoked"] is True


async def test_logout_revokes_the_session_row(client, seeded_user, db_session):
    await _login(client)
    await client.post("/auth/logout", headers=_headers(client))

    result = await db_session.execute(text("select revoked from sessions"))
    assert result.scalar_one() is True


async def test_logout_revokes_the_access_jti(client, seeded_user, redis_client):
    settings = get_settings()
    await _login(client)
    claims = decode_access_token(client.cookies[settings.access_cookie_name])

    await client.post("/auth/logout", headers=_headers(client))

    assert await redis_client.exists(f"revoked:jti:{claims['jti']}") == 1


async def test_logout_revokes_the_session_id_in_cache(client, seeded_user, redis_client):
    settings = get_settings()
    await _login(client)
    claims = decode_access_token(client.cookies[settings.access_cookie_name])

    await client.post("/auth/logout", headers=_headers(client))

    assert await redis_client.exists(f"revoked:sid:{claims['sid']}") == 1


async def test_logout_enqueues_a_session_end_event(client, seeded_user, db_session):
    await _login(client)
    await client.post("/auth/logout", headers=_headers(client))

    result = await db_session.execute(text("select count(*) from audit_outbox"))
    assert result.scalar_one() == 2


async def test_logout_clears_every_cookie(client, seeded_user):
    settings = get_settings()
    await _login(client)
    response = await client.post("/auth/logout", headers=_headers(client))

    cleared = [
        header for key, header in response.headers.multi_items() if key.lower() == "set-cookie"
    ]
    assert len(cleared) == 3
    for name in (
        settings.access_cookie_name,
        settings.refresh_cookie_name,
        settings.csrf_cookie_name,
    ):
        assert any(entry.startswith(f"{name}=") for entry in cleared)


async def test_logout_without_an_access_cookie_reports_nothing_revoked(client, seeded_user):
    settings = get_settings()
    await _login(client)
    headers = _headers(client)
    client.cookies.delete(settings.access_cookie_name)

    response = await client.post("/auth/logout", headers=headers)

    assert response.status_code == _OK
    assert response.json()["revoked"] is False


async def test_logout_with_a_malformed_token_reports_nothing_revoked(client, seeded_user):
    await _login(client)
    headers = _headers(client)
    _replace_access_cookie(client, "not-a-jwt")

    response = await client.post("/auth/logout", headers=headers)

    assert response.status_code == _OK
    assert response.json()["revoked"] is False


async def test_logout_with_a_malformed_token_still_clears_cookies(client, seeded_user):
    await _login(client)
    headers = _headers(client)
    _replace_access_cookie(client, "not-a-jwt")

    response = await client.post("/auth/logout", headers=headers)
    cleared = [key for key, _ in response.headers.multi_items() if key.lower() == "set-cookie"]

    assert len(cleared) == 3


async def test_logout_enqueues_no_further_events_without_a_session(client, seeded_user, db_session):
    await _login(client)
    await client.post("/auth/logout", headers=_headers(client))

    result = await db_session.execute(text("select count(*) from audit_outbox"))
    assert result.scalar_one() == 2


async def test_refresh_after_logout_is_rejected(client, seeded_user):
    settings = get_settings()
    await _login(client)
    csrf = client.cookies[settings.csrf_cookie_name]
    refresh_cookie = client.cookies[settings.refresh_cookie_name]

    await client.post("/auth/logout", headers=_headers(client))

    client.cookies.set(settings.csrf_cookie_name, csrf, domain=_DOMAIN, path="/")
    client.cookies.set(settings.refresh_cookie_name, refresh_cookie, domain=_DOMAIN, path="/")
    response = await client.post("/auth/refresh", headers={settings.csrf_header_name: csrf})

    assert response.status_code == 401
