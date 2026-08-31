from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.shared.schemas.alert import AlertMessage, AlertType, Severity
from app.shared.schemas.alertmanager import AlertmanagerWebhook
from app.shared.schemas.delivery import DeliverySource

Rendered = tuple[str, str | None]


def _readable_alert_type(value: AlertType) -> str:
    return value.value.replace("ALERT_TYPE_", "").lower().replace("_", " ")


def _readable_severity(value: Severity) -> str:
    return value.value.replace("SEVERITY_", "").lower().replace("_", " ")


def _render_alert(payload: dict[str, Any]) -> Rendered:
    alert = AlertMessage.model_validate(payload)
    if alert.alert_type == AlertType.ALERT_TYPE_CONCEALMENT:
        what = "possible concealment"
    elif alert.object is not None:
        what = f"person near {alert.object.class_name}"
    else:
        what = _readable_alert_type(alert.alert_type)
    severity = _readable_severity(alert.severity)
    camera_id = alert.camera_id or "default"
    occurred_at = alert.occurred_at.isoformat()
    text = (
        f"<b>theft-detection alert, {severity}</b>\n"
        f"{what}\n"
        f"camera: <code>{camera_id}</code>\n"
        f"time: {occurred_at}"
    )
    return text, alert.snapshot_path or None


def _render_alertmanager(payload: dict[str, Any]) -> Rendered:
    webhook = AlertmanagerWebhook.model_validate(payload)
    return webhook.to_telegram_html(), None


_RENDERERS: dict[DeliverySource, Callable[[dict[str, Any]], Rendered]] = {
    DeliverySource.ALERT: _render_alert,
    DeliverySource.ALERTMANAGER: _render_alertmanager,
}


def render(source: DeliverySource, payload: dict[str, Any]) -> Rendered:
    renderer = _RENDERERS.get(source)
    if renderer is None:
        raise ValueError(f"no renderer for source {source.value}")
    return renderer(payload)
