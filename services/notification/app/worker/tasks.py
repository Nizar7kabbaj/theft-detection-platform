from __future__ import annotations

import asyncio
import logging
from typing import Any

import requests
from pydantic import ValidationError

from app.core.database import (
    close_mongodb_connection,
    connect_to_mongodb,
    get_collection,
)
from app.repositories.dead_letter import DeadLetterRepository
from app.repositories.delivery_intent import DeliveryIntentRepository
from app.shared.celery_app import celery_app
from app.shared.config import settings
from app.shared.observability import inject_context
from app.shared.schemas.alert import AlertMessage, AlertType, Severity
from app.shared.schemas.delivery import (
    Channel,
    DeadLetterCreate,
    DeliveryIntentCreate,
    DeliverySource,
    DeliveryStatus,
)
from app.shared.telegram_service import send_message, send_photo

logger = logging.getLogger(__name__)

_UNCONFIGURED_RECIPIENT = "unconfigured"


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


def _dispatch(payload: AlertMessage, text: str) -> bool:
    if payload.snapshot_path:
        if send_photo(payload.snapshot_path, text):
            return True
    return send_message(text)


async def _deliver(payload: AlertMessage, final_attempt: bool) -> dict[str, Any]:
    await connect_to_mongodb()
    try:
        intent_repo = DeliveryIntentRepository(
            get_collection(settings.DELIVERY_INTENT_COLLECTION)
        )
        dlq_repo = DeadLetterRepository(
            get_collection(settings.DEAD_LETTER_COLLECTION)
        )

        recipient = settings.TELEGRAM_CHAT_ID or _UNCONFIGURED_RECIPIENT
        intent = await intent_repo.acquire(
            DeliveryIntentCreate(
                source=DeliverySource.ALERT,
                source_ref=payload.alert_id,
                channel=Channel.TELEGRAM,
                recipient=recipient,
                payload=payload.model_dump(mode="json"),
                trace_carrier=inject_context(),
            )
        )

        if intent.status == DeliveryStatus.SENT:
            logger.info("alert %s already sent, skipping", payload.alert_id)
            return {"alert_id": payload.alert_id, "delivered": True, "reason": "already_sent"}

        if recipient == _UNCONFIGURED_RECIPIENT:
            await intent_repo.mark_dead(intent.id, "telegram not configured")
            await dlq_repo.create(
                DeadLetterCreate(
                    source=intent.source,
                    source_ref=intent.source_ref,
                    channel=intent.channel,
                    recipient=intent.recipient,
                    payload=intent.payload,
                    trace_carrier=intent.trace_carrier,
                    attempts=intent.attempts,
                    last_error="telegram not configured",
                    intent_id=intent.id,
                )
            )
            logger.error("alert %s dead, telegram not configured", payload.alert_id)
            return {"alert_id": payload.alert_id, "delivered": False, "reason": "unconfigured"}

        claimed = await intent_repo.mark_sending(intent.id)
        if claimed is None:
            logger.info("alert %s claimed elsewhere, skipping", payload.alert_id)
            return {"alert_id": payload.alert_id, "delivered": False, "reason": "not_claimed"}

        text = _build_text(payload)
        try:
            sent = await asyncio.to_thread(_dispatch, payload, text)
        except requests.exceptions.RequestException as exc:
            error = str(exc)
            if final_attempt:
                await intent_repo.mark_dead(intent.id, error)
                await dlq_repo.create(
                    DeadLetterCreate(
                        source=intent.source,
                        source_ref=intent.source_ref,
                        channel=intent.channel,
                        recipient=intent.recipient,
                        payload=intent.payload,
                        trace_carrier=intent.trace_carrier,
                        attempts=claimed.attempts,
                        last_error=error,
                        intent_id=intent.id,
                    )
                )
                logger.error("alert %s dead after retries: %s", payload.alert_id, error)
                return {"alert_id": payload.alert_id, "delivered": False, "reason": "dead"}
            await intent_repo.mark_failed(intent.id, error)
            logger.warning("alert %s failed, will retry: %s", payload.alert_id, error)
            raise

        if not sent:
            await intent_repo.mark_dead(intent.id, "telegram declined")
            await dlq_repo.create(
                DeadLetterCreate(
                    source=intent.source,
                    source_ref=intent.source_ref,
                    channel=intent.channel,
                    recipient=intent.recipient,
                    payload=intent.payload,
                    trace_carrier=intent.trace_carrier,
                    attempts=claimed.attempts,
                    last_error="telegram declined",
                    intent_id=intent.id,
                )
            )
            logger.error("alert %s dead, telegram declined", payload.alert_id)
            return {"alert_id": payload.alert_id, "delivered": False, "reason": "declined"}

        await intent_repo.mark_sent(intent.id)
        logger.info("alert %s delivered", payload.alert_id)
        return {"alert_id": payload.alert_id, "delivered": True}
    finally:
        await close_mongodb_connection()


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
        logger.error("task received invalid payload: %s", exc.errors(include_url=False))
        return {"alert_id": alert.get("alert_id", "unknown"), "delivered": False, "reason": "validation"}

    final_attempt = self.request.retries >= self.max_retries
    logger.info("delivering alert %s attempt=%d", payload.alert_id, self.request.retries + 1)
    return asyncio.run(_deliver(payload, final_attempt))
