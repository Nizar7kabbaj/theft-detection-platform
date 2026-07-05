from __future__ import annotations

import logging
from typing import Any

import requests
from pydantic import ValidationError

from app.shared.celery_app import celery_app
from app.shared.config import settings
from app.shared.schemas.alert import AlertMessage, AlertType, Severity
from app.shared.telegram_service import send_message, send_photo

logger = logging.getLogger(__name__)


def _readable_alert_type(value: AlertType) -> str:
    return value.value.replace("ALERT_TYPE_", "").lower().replace("_", " ")


def _readable_severity(value: Severity) -> str:
    return value.value.replace("SEVERITY_", "").lower().replace("_", " ")


def _build_text(payload: AlertMessage) -> str:
    if payload.alert_type == AlertType.ALERT_TYPE_BENDING:
        what = "person bending, possible concealment"
    elif payload.object is not None:
        what = f"person near {payload.object.class_name}"
    else:
        what = _readable_alert_type(payload.alert_type)
    severity = _readable_severity(payload.severity)
    camera_id = payload.camera_id or "default"
    occurred_at = payload.occurred_at.isoformat()
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
    try:
        payload = AlertMessage.model_validate(alert)
    except ValidationError as exc:
        logger.error(
            "task received invalid payload: %s",
            exc.errors(include_url=False),
        )
        return {"alert_id": alert.get("alert_id", "unknown"), "delivered": False, "reason": "validation"}

    logger.info(
        "delivering alert %s attempt=%d",
        payload.alert_id,
        self.request.retries + 1,
    )
    text = _build_text(payload)
    if payload.snapshot_path:
        sent = send_photo(payload.snapshot_path, text)
        if not sent:
            sent = send_message(text)
    else:
        sent = send_message(text)
    if not sent:
        logger.warning("telegram delivery returned false for alert %s", payload.alert_id)
        return {"alert_id": payload.alert_id, "delivered": False}
    logger.info("alert %s delivered", payload.alert_id)
    return {"alert_id": payload.alert_id, "delivered": True}
