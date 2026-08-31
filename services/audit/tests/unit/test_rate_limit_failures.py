from __future__ import annotations

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.core import redis as redis_module
from app.core.config import get_settings

pytestmark = pytest.mark.unit


class BreakingRedis:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def incr(self, key: str) -> int:
        raise self.error

    async def pexpire(self, key: str, milliseconds: int) -> bool:
        return True


@pytest.fixture
def failing(monkeypatch: pytest.MonkeyPatch):
    def install(error: Exception) -> None:
        monkeypatch.setattr(redis_module, "get_redis", lambda: BreakingRedis(error))

    return install


@pytest.mark.parametrize(
    "error",
    [
        RedisConnectionError("refused"),
        RedisTimeoutError("timed out"),
        RedisError("generic"),
        OSError("socket closed"),
        TimeoutError("asyncio timeout"),
    ],
)
async def test_an_unreachable_redis_fails_open(
    failing, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    monkeypatch.setenv("AUDIT_APPEND_RATE_FAIL_CLOSED", "false")
    get_settings.cache_clear()
    failing(error)
    assert await redis_module.check_append_rate(1) is True


@pytest.mark.parametrize(
    "error",
    [
        RedisConnectionError("refused"),
        RedisTimeoutError("timed out"),
        RedisError("generic"),
        OSError("socket closed"),
        TimeoutError("asyncio timeout"),
    ],
)
async def test_an_unreachable_redis_fails_closed_when_configured(
    failing, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    monkeypatch.setenv("AUDIT_APPEND_RATE_FAIL_CLOSED", "true")
    get_settings.cache_clear()
    failing(error)
    assert await redis_module.check_append_rate(1) is False


async def test_a_programming_error_is_not_swallowed(
    failing, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUDIT_APPEND_RATE_FAIL_CLOSED", "false")
    get_settings.cache_clear()
    failing(TypeError("incr() got an unexpected keyword argument"))
    with pytest.raises(TypeError):
        await redis_module.check_append_rate(1)


async def test_an_attribute_error_is_not_swallowed(
    failing, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUDIT_APPEND_RATE_FAIL_CLOSED", "false")
    get_settings.cache_clear()
    failing(AttributeError("client has no attribute incr"))
    with pytest.raises(AttributeError):
        await redis_module.check_append_rate(1)


async def test_a_value_error_is_not_swallowed(failing, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDIT_APPEND_RATE_FAIL_CLOSED", "true")
    get_settings.cache_clear()
    failing(ValueError("malformed rate limit key"))
    with pytest.raises(ValueError, match="malformed rate limit key"):
        await redis_module.check_append_rate(1)


async def test_a_credential_error_is_not_swallowed(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("AUDIT_REDIS_PASSWORD_FILE", str(tmp_path / "absent"))
    get_settings.cache_clear()
    redis_module._load_redis_password.cache_clear()
    redis_module._client = None
    with pytest.raises(redis_module.RedisCredentialError):
        await redis_module.check_append_rate(1)
