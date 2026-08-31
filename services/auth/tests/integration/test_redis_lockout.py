from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.core.config import get_settings
from app.core.redis import (
    check_login,
    login_key,
    record_failure,
    reset_failures,
)

_MAX_ATTEMPTS = 3
_WINDOW_SECONDS = 60
_BLOCK_SECONDS = 300
_IP = "203.0.113.9"
_USER = "operator"


@pytest.fixture
def lockout_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("AUTH_LOGIN_MAX_ATTEMPTS", str(_MAX_ATTEMPTS))
    monkeypatch.setenv("AUTH_LOGIN_WINDOW_SECONDS", str(_WINDOW_SECONDS))
    monkeypatch.setenv("AUTH_LOGIN_BLOCK_SECONDS", str(_BLOCK_SECONDS))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_login_key_is_namespaced_by_ip_and_username():
    assert login_key(_IP, _USER) == f"login:fail:{_IP}:{_USER}"


async def test_no_failures_means_not_locked(redis_client, lockout_settings):
    locked, retry_ms = await check_login(_IP, _USER)

    assert locked is False
    assert retry_ms == 0


async def test_no_key_exists_before_a_failure(redis_client, lockout_settings):
    await check_login(_IP, _USER)

    assert await redis_client.exists(login_key(_IP, _USER)) == 0


async def test_failures_count_up(redis_client, lockout_settings):
    first_tripped, first_count = await record_failure(_IP, _USER)
    second_tripped, second_count = await record_failure(_IP, _USER)

    assert (first_tripped, first_count) == (False, 1)
    assert (second_tripped, second_count) == (False, 2)


async def test_trip_fires_once_at_the_limit(redis_client, lockout_settings):
    for _ in range(_MAX_ATTEMPTS - 1):
        await record_failure(_IP, _USER)

    tripped, count = await record_failure(_IP, _USER)

    assert tripped is True
    assert count == _MAX_ATTEMPTS


async def test_trip_does_not_fire_again_past_the_limit(redis_client, lockout_settings):
    for _ in range(_MAX_ATTEMPTS):
        await record_failure(_IP, _USER)

    tripped, count = await record_failure(_IP, _USER)

    assert tripped is False
    assert count == _MAX_ATTEMPTS + 1


async def test_below_the_limit_stays_unlocked(redis_client, lockout_settings):
    for _ in range(_MAX_ATTEMPTS - 1):
        await record_failure(_IP, _USER)

    locked, retry_ms = await check_login(_IP, _USER)

    assert locked is False
    assert retry_ms == 0


async def test_reaching_the_limit_locks_the_account(redis_client, lockout_settings):
    for _ in range(_MAX_ATTEMPTS):
        await record_failure(_IP, _USER)

    locked, retry_ms = await check_login(_IP, _USER)

    assert locked is True
    assert retry_ms > 0


async def test_window_expiry_is_applied_on_the_first_failure(redis_client, lockout_settings):
    await record_failure(_IP, _USER)
    ttl_ms = await redis_client.pttl(login_key(_IP, _USER))

    assert 0 < ttl_ms <= _WINDOW_SECONDS * 1000


async def test_block_expiry_replaces_the_window_at_the_limit(redis_client, lockout_settings):
    for _ in range(_MAX_ATTEMPTS):
        await record_failure(_IP, _USER)
    ttl_ms = await redis_client.pttl(login_key(_IP, _USER))

    assert ttl_ms > _WINDOW_SECONDS * 1000
    assert ttl_ms <= _BLOCK_SECONDS * 1000


async def test_further_failures_extend_the_block(redis_client, lockout_settings):
    for _ in range(_MAX_ATTEMPTS):
        await record_failure(_IP, _USER)
    key = login_key(_IP, _USER)
    await redis_client.pexpire(key, 1000)

    await record_failure(_IP, _USER)

    assert await redis_client.pttl(key) > _WINDOW_SECONDS * 1000


async def test_retry_hint_reports_the_remaining_block(redis_client, lockout_settings):
    for _ in range(_MAX_ATTEMPTS):
        await record_failure(_IP, _USER)

    _, retry_ms = await check_login(_IP, _USER)

    assert retry_ms > _WINDOW_SECONDS * 1000
    assert retry_ms <= _BLOCK_SECONDS * 1000


async def test_reset_clears_the_lockout(redis_client, lockout_settings):
    for _ in range(_MAX_ATTEMPTS):
        await record_failure(_IP, _USER)

    await reset_failures(_IP, _USER)
    locked, retry_ms = await check_login(_IP, _USER)

    assert locked is False
    assert retry_ms == 0
    assert await redis_client.exists(login_key(_IP, _USER)) == 0


async def test_reset_starts_the_count_again(redis_client, lockout_settings):
    await record_failure(_IP, _USER)
    await reset_failures(_IP, _USER)

    _, count = await record_failure(_IP, _USER)

    assert count == 1


async def test_reset_on_an_unknown_key_is_harmless(redis_client, lockout_settings):
    await reset_failures("198.51.100.7", "nobody")

    locked, _ = await check_login("198.51.100.7", "nobody")
    assert locked is False


async def test_lockout_is_isolated_per_username(redis_client, lockout_settings):
    for _ in range(_MAX_ATTEMPTS):
        await record_failure(_IP, _USER)

    locked, _ = await check_login(_IP, "someone-else")

    assert locked is False


async def test_lockout_is_isolated_per_ip(redis_client, lockout_settings):
    for _ in range(_MAX_ATTEMPTS):
        await record_failure(_IP, _USER)

    locked, _ = await check_login("198.51.100.7", _USER)

    assert locked is False
