from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.services.checkpoint_service import CheckpointResult, append_hook

pytestmark = pytest.mark.unit


async def test_the_hook_holds_below_the_threshold() -> None:
    threshold = get_settings().checkpoint_interval_events
    assert await append_hook(threshold - 1) is False


async def test_the_hook_fires_at_the_threshold() -> None:
    threshold = get_settings().checkpoint_interval_events
    assert await append_hook(threshold) is True


async def test_the_hook_fires_beyond_the_threshold() -> None:
    threshold = get_settings().checkpoint_interval_events
    assert await append_hook(threshold + 500) is True


async def test_the_hook_holds_at_zero() -> None:
    assert await append_hook(0) is False


async def test_the_threshold_follows_the_configured_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUDIT_CHECKPOINT_INTERVAL_EVENTS", "5")
    get_settings.cache_clear()
    assert await append_hook(4) is False
    assert await append_hook(5) is True


def test_the_result_carries_its_three_fields() -> None:
    result = CheckpointResult(2, 7, 3)
    assert result.failure_kind == 2
    assert result.checkpoints_verified == 7
    assert result.break_at_checkpoint_id == 3
