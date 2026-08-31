from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core import database as database_module
from app.core.config import get_settings
from app.core.security import hash_password
from app.main import create_app
from app.repositories.user_repository import UserRepository

_PASSWORD = "harness-password"
_USERNAME = "operator"
_OK = 200
_UNAUTHORIZED = 401
_FORBIDDEN = 403
_TOO_MANY = 429
_UNPROCESSABLE = 422


@pytest.fixture(autouse=True)
async def app_resources(redis_client, db_session) -> AsyncIterator[None]:
    yield
    await database_module.dispose_engine()
    database_module._sessionmaker = None


@pytest.fixture
async def seeded_user(db_session):
    user = await UserRepository(db_session).create(
        username=_USERNAME,
        password_hash=hash_password(_PASSWORD),
        roles=["operator"],
    )
    await db_session.commit()
    return user


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="https://testserver") as http:
        yield http


async def _login(client: AsyncClient, password: str = _PASSWORD, username: str = _USERNAME):
    return await client.post("/auth/login", json={"username": username, "password": password})


def _csrf_headers(client: AsyncClient) -> dict[str, str]:
    settings = get_settings()
    return {settings.csrf_header_name: client.cookies[settings.csrf_cookie_name]}


async def test_login_succeeds_with_valid_credentials(client, seeded_user):
    response = await _login(client)

    assert response.status_code == _OK
    assert response.json()["token_type"] == "Bearer"
    assert response.json()["expires_in"] == get_settings().access_token_ttl_seconds


async def test_login_sets_all_three_cookies(client, seeded_user):
    settings = get_settings()
    await _login(client)

    assert settings.access_cookie_name in client.cookies
    assert settings.refresh_cookie_name in client.cookies
    assert settings.csrf_cookie_name in client.cookies


async def test_login_creates_a_session_row(client, seeded_user, db_session):
    await _login(client)
    result = await db_session.execute(text("select count(*) from sessions"))

    assert result.scalar_one() == 1


async def test_login_creates_a_refresh_token_row(client, seeded_user, db_session):
    await _login(client)
    result = await db_session.execute(text("select count(*) from refresh_tokens"))

    assert result.scalar_one() == 1


async def test_login_enqueues_an_audit_event(client, seeded_user, db_session):
    await _login(client)
    result = await db_session.execute(text("select count(*) from audit_outbox"))

    assert result.scalar_one() == 1


async def test_refresh_token_is_never_stored_in_plain_text(client, seeded_user, db_session):
    await _login(client)
    raw = client.cookies[get_settings().refresh_cookie_name]
    secret = raw.split(".", 1)[1]
    result = await db_session.execute(text("select token_hash from refresh_tokens"))

    assert secret not in result.scalar_one()


async def test_unknown_user_is_rejected(client):
    response = await _login(client, username="nobody")

    assert response.status_code == _UNAUTHORIZED
    assert response.json()["detail"] == "invalid credentials"


async def test_wrong_password_is_rejected(client, seeded_user):
    response = await _login(client, password="wrong-password")

    assert response.status_code == _UNAUTHORIZED
    assert response.json()["detail"] == "invalid credentials"


async def test_failed_login_sets_no_cookies(client, seeded_user):
    response = await _login(client, password="wrong-password")

    assert response.cookies == {}


async def test_failed_login_enqueues_an_audit_event(client, seeded_user, db_session):
    await _login(client, password="wrong-password")
    result = await db_session.execute(text("select count(*) from audit_outbox"))

    assert result.scalar_one() == 1


async def test_unknown_user_failure_is_also_audited(client, db_session):
    await _login(client, username="nobody")
    result = await db_session.execute(text("select count(*) from audit_outbox"))

    assert result.scalar_one() == 1


async def test_repeated_failures_lock_the_account(client, seeded_user):
    settings = get_settings()
    for _ in range(settings.login_max_attempts):
        await _login(client, password="wrong-password")

    response = await _login(client, password="wrong-password")

    assert response.status_code == _TOO_MANY
    assert int(response.headers["retry-after"]) > 0


async def test_lockout_blocks_the_correct_password_too(client, seeded_user):
    settings = get_settings()
    for _ in range(settings.login_max_attempts):
        await _login(client, password="wrong-password")

    assert (await _login(client)).status_code == _TOO_MANY


async def test_successful_login_clears_the_failure_count(client, seeded_user, redis_client):
    from app.core.redis import login_key

    await _login(client, password="wrong-password")
    await _login(client)

    assert await redis_client.exists(login_key("", _USERNAME)) == 0


async def test_missing_password_is_rejected_by_validation(client):
    response = await client.post("/auth/login", json={"username": _USERNAME})

    assert response.status_code == _UNPROCESSABLE


async def test_extra_fields_are_rejected(client, seeded_user):
    response = await client.post(
        "/auth/login",
        json={"username": _USERNAME, "password": _PASSWORD, "role": "admin"},
    )

    assert response.status_code == _UNPROCESSABLE


async def test_refresh_without_csrf_header_is_forbidden(client, seeded_user):
    await _login(client)
    response = await client.post("/auth/refresh")

    assert response.status_code == _FORBIDDEN


async def test_refresh_with_wrong_csrf_header_is_forbidden(client, seeded_user):
    settings = get_settings()
    await _login(client)
    response = await client.post(
        "/auth/refresh", headers={settings.csrf_header_name: "not-the-token"}
    )

    assert response.status_code == _FORBIDDEN


async def test_logout_without_csrf_header_is_forbidden(client, seeded_user):
    await _login(client)
    response = await client.post("/auth/logout")

    assert response.status_code == _FORBIDDEN


async def test_health_endpoint_reports_ok(client):
    response = await client.get("/health")

    assert response.status_code == _OK
    assert response.json() == {"status": "ok"}
