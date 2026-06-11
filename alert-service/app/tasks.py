from __future__ import annotations

import logging
from typing import Any

import requests

from app.celery_app import celery_app
from app.core.config import settings
from app.telegram_service import send_message, send_photo

logger = logging.getLogger(__name__)


def _build_text(alert: dict[str, Any]) -> str:
    alert_type = alert.get("alert_type") or "object_proximity"
    obj = alert.get("object") or {}

    if alert_type == "bending":
        what = "person bending, possible concealment"
    elif obj:
        class_name = obj.get("class_name", "object")
        what = f"person near {class_name}"
    else:
        what = alert_type

    severity = alert.get("severity", "medium")
    camera_id = alert.get("camera_id", "default")
    timestamp = alert.get("timestamp", "")
    torso_angle = alert.get("torso_angle")

    angle_line = ""
    if torso_angle is not None:
        angle_line = f"\ntorso angle: <b>{torso_angle:.1f}°</b>"

    return (
        f"<b>theft-detection alert, {severity}</b>\n"
        f"{what}\n"
        f"camera: <code>{camera_id}</code>\n"
        f"time: {timestamp}"
        f"{angle_line}"
    )


@celery_app.task(
    name="app.tasks.send_alert_task",
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
