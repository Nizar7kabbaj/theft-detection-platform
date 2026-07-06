from __future__ import annotations

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
    text, photo = render(DeliverySource.ALERT, alert_payload)
    assert "backpack" in text
    assert photo == "/tmp/snap.jpg"


def test_render_alert_bending(alert_payload) -> None:
    text, photo = render(DeliverySource.ALERT, alert_payload)
    assert "bending" in text
    assert photo is None


def test_render_alert_invalid_raises() -> None:
    with pytest.raises(ValidationError):
        render(DeliverySource.ALERT, {"session_id": 1, "occurred_at": "2026-06-18T00:00:00Z"})


def test_render_alertmanager(alertmanager_payload) -> None:
    text, photo = render(DeliverySource.ALERTMANAGER, alertmanager_payload)
    assert text
    assert photo is None


def test_render_unknown_source_raises(monkeypatch) -> None:
    monkeypatch.delitem(renderers._RENDERERS, DeliverySource.ALERT, raising=False)
    with pytest.raises(ValueError, match="no renderer"):
        render(DeliverySource.ALERT, {})
