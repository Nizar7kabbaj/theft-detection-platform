from __future__ import annotations

import pytest
from redis.exceptions import NoPermissionError

from app.core.redis import login_key


async def test_acl_introspection_is_refused(redis_client):
    with pytest.raises(NoPermissionError):
        await redis_client.execute_command("ACL", "WHOAMI")


async def test_granted_login_key_pattern_is_writable(redis_client):
    key = login_key("203.0.113.9", "operator")
    await redis_client.set(key, "1")

    assert await redis_client.get(key) == "1"


async def test_granted_revocation_key_pattern_is_writable(redis_client):
    await redis_client.set("revoked:jti:abc", "1")

    assert await redis_client.exists("revoked:jti:abc") == 1


async def test_ungranted_key_pattern_is_refused(redis_client):
    with pytest.raises(NoPermissionError):
        await redis_client.set("session:data:abc", "1")


async def test_revocation_channel_publish_is_permitted(redis_client):
    assert await redis_client.publish("session:revoked", "session-id") == 0


async def test_ungranted_channel_publish_is_refused(redis_client):
    with pytest.raises(NoPermissionError):
        await redis_client.publish("alerts", "payload")


async def test_scripting_is_permitted(redis_client):
    script = redis_client.register_script("return 1")

    assert await script(keys=[], args=[]) == 1


async def test_dangerous_commands_are_refused(redis_client):
    with pytest.raises(NoPermissionError):
        await redis_client.execute_command("CONFIG", "GET", "maxmemory")
