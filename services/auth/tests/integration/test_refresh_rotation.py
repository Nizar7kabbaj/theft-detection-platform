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


_DOMAIN = "testserver.local"


def _headers(client: AsyncClient) -> dict[str, str]:
    settings = get_settings()
    return {settings.csrf_header_name: client.cookies[settings.csrf_cookie_name]}


def _replace_refresh_cookie(client: AsyncClient, value: str) -> None:
    settings = get_settings()
    client.cookies.delete(settings.refresh_cookie_name)
    client.cookies.set(settings.refresh_cookie_name, value, domain=_DOMAIN, path="/")


async def _login(client: AsyncClient) -> None:
    await client.post("/auth/login", json={"username": _USERNAME, "password": _PASSWORD})


def _refresh_cookie(client: AsyncClient) -> str:
    return client.cookies[get_settings().refresh_cookie_name]


async def test_refresh_succeeds_after_login(client, seeded_user):
    await _login(client)
    response = await client.post("/auth/refresh", headers=_headers(client))

    assert response.status_code == _OK
    assert response.json()["expires_in"] == get_settings().access_token_ttl_seconds


async def test_refresh_issues_a_new_refresh_token(client, seeded_user):
    await _login(client)
    original = _refresh_cookie(client)
    await client.post("/auth/refresh", headers=_headers(client))

    assert _refresh_cookie(client) != original


async def test_refresh_rotates_the_csrf_token(client, seeded_user):
    settings = get_settings()
    await _login(client)
    original = client.cookies[settings.csrf_cookie_name]
    await client.post("/auth/refresh", headers=_headers(client))

    assert client.cookies[settings.csrf_cookie_name] != original


async def test_rotation_keeps_the_family_and_records_the_link(client, seeded_user, db_session):
    await _login(client)
    await client.post("/auth/refresh", headers=_headers(client))

    result = await db_session.execute(
        text("select jti, family_id, rotated_from, revoked from refresh_tokens order by created_at")
    )
    rows = result.all()

    assert len(rows) == 2
    assert str(rows[0][1]) == str(rows[1][1])
    assert str(rows[1][2]) == str(rows[0][0])
    assert rows[0][3] is True
    assert rows[1][3] is False


async def test_rotation_reuses_the_same_session(client, seeded_user, db_session):
    await _login(client)
    await client.post("/auth/refresh", headers=_headers(client))
    result = await db_session.execute(text("select count(*) from sessions"))

    assert result.scalar_one() == 1


async def test_rotation_enqueues_an_audit_event(client, seeded_user, db_session):
    await _login(client)
    await client.post("/auth/refresh", headers=_headers(client))
    result = await db_session.execute(text("select count(*) from audit_outbox"))

    assert result.scalar_one() == 2


async def test_repeated_rotation_chains_correctly(client, seeded_user, db_session):
    await _login(client)
    for _ in range(3):
        assert (await client.post("/auth/refresh", headers=_headers(client))).status_code == _OK

    result = await db_session.execute(text("select count(*) from refresh_tokens"))
    assert result.scalar_one() == 4


async def test_replayed_token_inside_grace_window_is_accepted(client, seeded_user):
    await _login(client)
    replayed = _refresh_cookie(client)
    await client.post("/auth/refresh", headers=_headers(client))

    _replace_refresh_cookie(client, replayed)
    response = await client.post("/auth/refresh", headers=_headers(client))

    assert response.status_code == _OK


async def test_stale_token_outside_grace_window_is_rejected(client, seeded_user, db_session):
    await _login(client)
    stale = _refresh_cookie(client)
    await client.post("/auth/refresh", headers=_headers(client))

    await db_session.execute(
        text("update refresh_tokens set rotated_at = now() - interval '1 hour'")
    )
    await db_session.commit()

    _replace_refresh_cookie(client, stale)
    response = await client.post("/auth/refresh", headers=_headers(client))

    assert response.status_code == _UNAUTHORIZED
    assert response.json()["detail"]["code"] == "session_invalid"


async def test_reuse_revokes_the_whole_family(client, seeded_user, db_session):
    await _login(client)
    stale = _refresh_cookie(client)
    await client.post("/auth/refresh", headers=_headers(client))

    await db_session.execute(
        text("update refresh_tokens set rotated_at = now() - interval '1 hour'")
    )
    await db_session.commit()

    _replace_refresh_cookie(client, stale)
    await client.post("/auth/refresh", headers=_headers(client))

    result = await db_session.execute(
        text("select count(*) from refresh_tokens where revoked = false")
    )
    assert result.scalar_one() == 0


async def test_reuse_revokes_the_session(client, seeded_user, db_session):
    await _login(client)
    stale = _refresh_cookie(client)
    await client.post("/auth/refresh", headers=_headers(client))

    await db_session.execute(
        text("update refresh_tokens set rotated_at = now() - interval '1 hour'")
    )
    await db_session.commit()

    _replace_refresh_cookie(client, stale)
    await client.post("/auth/refresh", headers=_headers(client))

    result = await db_session.execute(text("select revoked from sessions"))
    assert result.scalar_one() is True


async def test_reuse_enqueues_a_critical_audit_event(client, seeded_user, db_session):
    await _login(client)
    stale = _refresh_cookie(client)
    await client.post("/auth/refresh", headers=_headers(client))

    await db_session.execute(
        text("update refresh_tokens set rotated_at = now() - interval '1 hour'")
    )
    await db_session.commit()

    _replace_refresh_cookie(client, stale)
    await client.post("/auth/refresh", headers=_headers(client))

    result = await db_session.execute(text("select count(*) from audit_outbox"))
    assert result.scalar_one() == 3


async def test_refresh_without_a_cookie_is_rejected(client, seeded_user):
    await _login(client)
    settings = get_settings()
    headers = _headers(client)
    client.cookies.delete(settings.refresh_cookie_name)

    response = await client.post("/auth/refresh", headers=headers)

    assert response.status_code == _UNAUTHORIZED


async def test_malformed_refresh_cookie_is_rejected(client, seeded_user):
    await _login(client)
    _replace_refresh_cookie(client, "no-separator")

    response = await client.post("/auth/refresh", headers=_headers(client))

    assert response.status_code == _UNAUTHORIZED


async def test_unknown_refresh_token_is_rejected(client, seeded_user):
    await _login(client)
    _replace_refresh_cookie(client, "11111111-1111-1111-1111-111111111111.some-secret")

    response = await client.post("/auth/refresh", headers=_headers(client))

    assert response.status_code == _UNAUTHORIZED


async def test_wrong_secret_for_known_jti_is_rejected(client, seeded_user, db_session):
    await _login(client)
    jti = _refresh_cookie(client).split(".", 1)[0]
    _replace_refresh_cookie(client, f"{jti}.wrong-secret")

    response = await client.post("/auth/refresh", headers=_headers(client))

    assert response.status_code == _UNAUTHORIZED


async def test_disabled_account_cannot_refresh(client, seeded_user, db_session):
    await _login(client)
    await db_session.execute(text("update users set is_active = false"))
    await db_session.commit()

    response = await client.post("/auth/refresh", headers=_headers(client))

    assert response.status_code == _UNAUTHORIZED
    assert response.json()["detail"]["code"] == "account_disabled"


async def test_revoked_session_cannot_refresh(client, seeded_user, db_session):
    await _login(client)
    await db_session.execute(text("update sessions set revoked = true"))
    await db_session.commit()

    response = await client.post("/auth/refresh", headers=_headers(client))

    assert response.status_code == _UNAUTHORIZED
    assert response.json()["detail"]["code"] == "session_invalid"


async def test_expired_refresh_token_is_rejected(client, seeded_user, db_session):
    await _login(client)
    await db_session.execute(
        text("update refresh_tokens set expires_at = now() - interval '1 day'")
    )
    await db_session.commit()

    response = await client.post("/auth/refresh", headers=_headers(client))

    assert response.status_code == _UNAUTHORIZED
