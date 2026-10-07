from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.shared.schemas.delivery import DeliverySource
from app.worker import renderers
from app.worker.renderers import render

pytestmark = pytest.mark.unit


def test_render_alert_object_proximity(alert_payload) -> None:
    alert_payload["alert_type"] = "ALERT_TYPE_OBJECT_PROXIMITY"
    alert_payload["object"] = {"class_name": "backpack"}
    alert_payload["snapshot_path"] = "/tmp/snap.jpg"
    text, photo, clip = render(DeliverySource.ALERT, alert_payload)
    assert "backpack" in text
    assert photo == "/tmp/snap.jpg"
    assert clip is None


def test_render_alert_concealment(alert_payload) -> None:
    text, photo, _clip = render(DeliverySource.ALERT, alert_payload)
    assert "concealment" in text
    assert photo is None


def test_render_alert_invalid_raises() -> None:
    with pytest.raises(ValidationError):
        render(DeliverySource.ALERT, {"session_id": 1, "occurred_at": "2026-06-18T00:00:00Z"})


def test_render_alertmanager(alertmanager_payload) -> None:
    text, photo, clip = render(DeliverySource.ALERTMANAGER, alertmanager_payload)
    assert text
    assert photo is None
    assert clip is None


def test_render_unknown_source_raises(monkeypatch) -> None:
    monkeypatch.delitem(renderers._RENDERERS, DeliverySource.ALERT, raising=False)
    with pytest.raises(ValueError, match="no renderer"):
        render(DeliverySource.ALERT, {})


def test_decision_outcome_escapes_the_operator_name() -> None:
    line = renderers.render_decision_outcome(
        "DECISION_CONFIRMED", "<b>x", datetime(2026, 10, 7, 11, 43, tzinfo=UTC)
    )
    assert "&lt;b&gt;x" in line
    assert "<b>confirmed</b>" in line
    assert "2026-10-07 11:43 UTC" in line


def test_decision_outcome_without_a_name_says_unknown() -> None:
    line = renderers.render_decision_outcome(
        "DECISION_UNSURE", "", datetime(2026, 10, 7, tzinfo=UTC)
    )
    assert "unknown" in line
