from __future__ import annotations

from app.schemas.policy import PolicyPayload
from app.services.policy_sync import (
    POLICY_CHANNEL,
    POLICY_CURRENT_KEY,
    PUBLISH_NEWER_LUA,
    _sync_once,
    policy_message,
    publish_policy,
)


def _stream(mocker, result: int):
    stream = mocker.Mock()
    script = mocker.AsyncMock(return_value=result)
    stream.register_script = mocker.Mock(return_value=script)
    return stream, script


async def test_publish_policy_runs_newer_only_script(mocker) -> None:
    stream, script = _stream(mocker, 1)

    assert await publish_policy(stream, 6, "body") is True
    stream.register_script.assert_called_once_with(PUBLISH_NEWER_LUA)
    script.assert_awaited_once_with(keys=[POLICY_CURRENT_KEY], args=[6, "body", POLICY_CHANNEL])


async def test_publish_policy_reports_stale_version(mocker) -> None:
    stream, _ = _stream(mocker, 0)

    assert await publish_policy(stream, 5, "body") is False


async def test_sync_once_offers_mongo_version(mocker) -> None:
    stream, script = _stream(mocker, 1)
    repo = mocker.Mock()
    repo.current = mocker.AsyncMock(
        return_value={"version": 3, "policy": PolicyPayload().model_dump()}
    )

    await _sync_once(repo, stream)

    assert script.call_args.kwargs["args"] == [
        3,
        policy_message(3, PolicyPayload()),
        POLICY_CHANNEL,
    ]


async def test_sync_once_skips_without_policy(mocker) -> None:
    stream, script = _stream(mocker, 1)
    repo = mocker.Mock()
    repo.current = mocker.AsyncMock(return_value=None)

    await _sync_once(repo, stream)

    script.assert_not_awaited()
