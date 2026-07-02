from __future__ import annotations
import logging
from typing import Any
import requests
from app.shared.celery_app import celery_app
from app.shared.config import settings
from app.shared.telegram_service import send_message, send_photo
logger = logging.getLogger(__name__)


def _readable(value: str, prefix: str) -> str:
    return value.replace(prefix, "").lower().replace("_", " ")


def _readable_alert_type(value: str | None) -> str:
    if not value:
        return "unspecified"
    return _readable(value, "ALERT_TYPE_")


def _readable_severity(value: str | None) -> str:
    if not value:
        return "notice"
    return _readable(value, "SEVERITY_")


def _extract_occurred_at(alert: dict[str, Any]) -> str:
    raw = alert.get("occurred_at") or alert.get("timestamp") or ""
    if hasattr(raw, "isoformat"):
        return raw.isoformat()
    return str(raw)


def _build_text(alert: dict[str, Any]) -> str:
    alert_type_raw = alert.get("alert_type") or "ALERT_TYPE_OBJECT_PROXIMITY"
    obj = alert.get("object") or {}
    if alert_type_raw == "ALERT_TYPE_BENDING":
        what = "person bending, possible concealment"
    elif obj:
        class_name = obj.get("class_name", "object")
        what = f"person near {class_name}"
    else:
        what = _readable_alert_type(alert_type_raw)
    severity = _readable_severity(alert.get("severity"))
    camera_id = alert.get("camera_id", "default")
    occurred_at = _extract_occurred_at(alert)
    return (
        f"<b>theft-detection alert, {severity}</b>\n"
        f"{what}\n"
        f"camera: <code>{camera_id}</code>\n"
        f"time: {occurred_at}"
    )


@celery_app.task(
    name="app.worker.tasks.send_alert_task",
    bind=True,
    max_retries=settings.CELERY_TASK_MAX_RETRIES,
    default_retry_delay=settings.CELERY_TASK_RETRY_DELAY_SEC,
    autoretry_for=(requests.exceptions.RequestException,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    acks_late=True,
)
def send_alert_task(self, alert: dict[str, Any]) -> dict[str, Any]:
    alert_id = alert.get("alert_id", "unknown")
    logger.info("delivering alert %s attempt=%d", alert_id, self.request.retries + 1)
    text = _build_text(alert)
    snapshot = alert.get("snapshot_path")
    if snapshot:
        sent = send_photo(snapshot, text)
        if not sent:
            sent = send_message(text)
    else:
        sent = send_message(text)
    if not sent:
        logger.warning("telegram delivery returned false for alert %s", alert_id)
        return {"alert_id": alert_id, "delivered": False}
    logger.info("alert %s delivered", alert_id)
    return {"alert_id": alert_id, "delivered": True}
