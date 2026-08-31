from __future__ import annotations

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError

from app.core import redis as redis_module
from app.core.config import get_settings
from tests import REDIS_PASSWORD_FILE

pytestmark = pytest.mark.unit


class FakeRedis:
    def __init__(self) -> None:
        self.counters: dict[str, int] = {}
        self.expiries: dict[str, int] = {}
        self.incr_calls: list[str] = []
        self.incr_error: Exception | None = None
        self.pexpire_error: Exception | None = None

    async def incr(self, key: str) -> int:
        self.incr_calls.append(key)
        if self.incr_error is not None:
            raise self.incr_error
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    async def pexpire(self, key: str, milliseconds: int) -> bool:
        if self.pexpire_error is not None:
            raise self.pexpire_error
        self.expiries[key] = milliseconds
        return True

    async def aclose(self) -> None:
        return None


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> FakeRedis:
    client = FakeRedis()
    monkeypatch.setattr(redis_module, "get_redis", lambda: client)
    return client


@pytest.fixture
def frozen_clock(monkeypatch: pytest.MonkeyPatch) -> dict[str, float]:
    clock = {"now": 1_700_000_000.0}
    monkeypatch.setattr(redis_module.time, "time", lambda: clock["now"])
    return clock


def test_rate_limit_key_includes_service_and_window() -> None:
    assert redis_module.rate_limit_key(3, 42) == "audit:rl:3:42"


def test_rate_limit_keys_differ_between_services() -> None:
    assert redis_module.rate_limit_key(1, 42) != redis_module.rate_limit_key(2, 42)


def test_rate_limit_keys_differ_between_windows() -> None:
    assert redis_module.rate_limit_key(1, 42) != redis_module.rate_limit_key(1, 43)


async def test_first_append_is_allowed(fake_redis: FakeRedis) -> None:
    assert await redis_module.check_append_rate(1) is True


async def test_first_append_sets_an_expiry(
    fake_redis: FakeRedis, frozen_clock: dict[str, float]
) -> None:
    await redis_module.check_append_rate(1)
    key = redis_module.rate_limit_key(1, int(frozen_clock["now"]))
    assert fake_redis.expiries[key] == 2000


async def test_expiry_is_set_only_on_the_first_append(fake_redis: FakeRedis) -> None:
    await redis_module.check_append_rate(1)
    fake_redis.expiries.clear()
    await redis_module.check_append_rate(1)
    assert fake_redis.expiries == {}


async def test_appends_within_the_limit_are_allowed(
    fake_redis: FakeRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUDIT_APPEND_RATE_LIMIT", "3")
    get_settings.cache_clear()
    results = [await redis_module.check_append_rate(1) for _ in range(3)]
    assert results == [True, True, True]


async def test_append_beyond_the_limit_is_refused(
    fake_redis: FakeRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUDIT_APPEND_RATE_LIMIT", "3")
    get_settings.cache_clear()
    for _ in range(3):
        await redis_module.check_append_rate(1)
    assert await redis_module.check_append_rate(1) is False


async def test_a_limit_of_zero_refuses_everything(
    fake_redis: FakeRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUDIT_APPEND_RATE_LIMIT", "0")
    get_settings.cache_clear()
    assert await redis_module.check_append_rate(1) is False


async def test_services_are_counted_separately(
    fake_redis: FakeRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUDIT_APPEND_RATE_LIMIT", "1")
    get_settings.cache_clear()
    assert await redis_module.check_append_rate(1) is True
    assert await redis_module.check_append_rate(2) is True
    assert await redis_module.check_append_rate(1) is False


async def test_counter_resets_when_the_window_rolls(
    fake_redis: FakeRedis, frozen_clock: dict[str, float], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUDIT_APPEND_RATE_LIMIT", "1")
    get_settings.cache_clear()
    assert await redis_module.check_append_rate(1) is True
    assert await redis_module.check_append_rate(1) is False
    frozen_clock["now"] += 1.0
    assert await redis_module.check_append_rate(1) is True


async def test_window_is_derived_from_the_configured_span(
    fake_redis: FakeRedis, frozen_clock: dict[str, float], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUDIT_APPEND_RATE_WINDOW_SECONDS", "60")
    get_settings.cache_clear()
    await redis_module.check_append_rate(1)
    expected = redis_module.rate_limit_key(1, int(frozen_clock["now"]) // 60)
    assert fake_redis.incr_calls == [expected]


async def test_a_longer_window_holds_the_counter_across_seconds(
    fake_redis: FakeRedis, frozen_clock: dict[str, float], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUDIT_APPEND_RATE_WINDOW_SECONDS", "60")
    monkeypatch.setenv("AUDIT_APPEND_RATE_LIMIT", "1")
    get_settings.cache_clear()
    assert await redis_module.check_append_rate(1) is True
    frozen_clock["now"] += 5.0
    assert await redis_module.check_append_rate(1) is False


async def test_expiry_scales_with_the_window(
    fake_redis: FakeRedis, frozen_clock: dict[str, float], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUDIT_APPEND_RATE_WINDOW_SECONDS", "60")
    get_settings.cache_clear()
    await redis_module.check_append_rate(1)
    key = redis_module.rate_limit_key(1, int(frozen_clock["now"]) // 60)
    assert fake_redis.expiries[key] == 120000


async def test_a_zero_window_falls_back_to_one_second(
    fake_redis: FakeRedis, frozen_clock: dict[str, float], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUDIT_APPEND_RATE_WINDOW_SECONDS", "0")
    get_settings.cache_clear()
    await redis_module.check_append_rate(1)
    expected = redis_module.rate_limit_key(1, int(frozen_clock["now"]))
    assert fake_redis.incr_calls == [expected]


async def test_redis_failure_allows_the_append_when_failing_open(
    fake_redis: FakeRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUDIT_APPEND_RATE_FAIL_CLOSED", "false")
    get_settings.cache_clear()
    fake_redis.incr_error = RedisConnectionError("redis unreachable")
    assert await redis_module.check_append_rate(1) is True


async def test_redis_failure_refuses_the_append_when_failing_closed(
    fake_redis: FakeRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUDIT_APPEND_RATE_FAIL_CLOSED", "true")
    get_settings.cache_clear()
    fake_redis.incr_error = RedisConnectionError("redis unreachable")
    assert await redis_module.check_append_rate(1) is False


async def test_redis_error_does_not_escape(
    fake_redis: FakeRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUDIT_APPEND_RATE_FAIL_CLOSED", "false")
    get_settings.cache_clear()
    fake_redis.incr_error = RedisError("broken")
    assert await redis_module.check_append_rate(1) is True


async def test_a_failing_expiry_does_not_refuse_the_append(
    fake_redis: FakeRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUDIT_APPEND_RATE_FAIL_CLOSED", "false")
    get_settings.cache_clear()
    fake_redis.pexpire_error = RedisConnectionError("redis unreachable")
    assert await redis_module.check_append_rate(1) is True


async def test_a_non_redis_failure_is_also_contained(
    fake_redis: FakeRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUDIT_APPEND_RATE_FAIL_CLOSED", "true")
    get_settings.cache_clear()
    fake_redis.incr_error = TimeoutError("socket timeout")
    assert await redis_module.check_append_rate(1) is False


def test_redis_password_is_read_from_the_configured_file() -> None:
    assert redis_module._load_redis_password() == REDIS_PASSWORD_FILE.read_text().strip()


def test_missing_redis_password_file_is_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("AUDIT_REDIS_PASSWORD_FILE", str(tmp_path / "absent"))
    get_settings.cache_clear()
    redis_module._load_redis_password.cache_clear()
    with pytest.raises(redis_module.RedisCredentialError, match="missing"):
        redis_module._load_redis_password()


def test_empty_redis_password_file_is_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    empty = tmp_path / "empty_password"
    empty.write_text("  \n", encoding="utf-8")
    monkeypatch.setenv("AUDIT_REDIS_PASSWORD_FILE", str(empty))
    get_settings.cache_clear()
    redis_module._load_redis_password.cache_clear()
    with pytest.raises(redis_module.RedisCredentialError, match="empty"):
        redis_module._load_redis_password()


def test_unreadable_redis_password_file_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    directory = tmp_path / "password_directory"
    directory.mkdir()
    monkeypatch.setenv("AUDIT_REDIS_PASSWORD_FILE", str(directory))
    get_settings.cache_clear()
    redis_module._load_redis_password.cache_clear()
    with pytest.raises(redis_module.RedisCredentialError, match="unreadable"):
        redis_module._load_redis_password()


def test_tls_options_are_empty_when_tls_is_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDIT_REDIS_TLS", "false")
    get_settings.cache_clear()
    assert redis_module._tls_options() == {}


def test_tls_options_require_a_verified_peer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDIT_REDIS_TLS", "true")
    get_settings.cache_clear()
    options = redis_module._tls_options()
    assert options["ssl"] is True
    assert options["ssl_cert_reqs"] == "required"


def test_tls_options_carry_the_client_certificate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDIT_REDIS_TLS", "true")
    get_settings.cache_clear()
    settings = get_settings()
    options = redis_module._tls_options()
    assert options["ssl_certfile"] == str(settings.tls_cert_file)
    assert options["ssl_keyfile"] == str(settings.tls_key_file)
    assert options["ssl_ca_certs"] == str(settings.tls_ca_file)
