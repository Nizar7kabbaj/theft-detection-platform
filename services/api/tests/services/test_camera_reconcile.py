from __future__ import annotations

import json

from redis.exceptions import RedisError

from app.services.camera_health import CameraHealth, HealthState
from app.services.camera_reconcile import _publish_if_changed, state_key


async def test_transition_carries_state_observation_and_ttl(mocker) -> None:
    script = mocker.AsyncMock(return_value=1)
    health = CameraHealth(HealthState.ONLINE, 100.0, 0.5)

    assert await _publish_if_changed(script, "cam-1", health, 1700, 30) is True

    kwargs = script.call_args.kwargs
    assert kwargs["keys"] == [state_key("cam-1")] == ["health:camera:cam-1"]
    state, observed, ttl, channel, payload = kwargs["args"]
    assert (state, observed, ttl, channel) == (HealthState.ONLINE.value, 1700, 30, "cameras:health")
    assert json.loads(payload)["camera_id"] == "cam-1"


async def test_unchanged_state_reports_no_publish(mocker) -> None:
    script = mocker.AsyncMock(return_value=0)
    health = CameraHealth(HealthState.ONLINE, 100.0, 0.5)

    assert await _publish_if_changed(script, "cam-1", health, 1700, 30) is False


async def test_redis_error_is_contained(mocker) -> None:
    script = mocker.AsyncMock(side_effect=RedisError("down"))
    health = CameraHealth(HealthState.OFFLINE, None, None)

    assert await _publish_if_changed(script, "cam-1", health, 1700, 30) is False
