import asyncio
import logging
import secrets
import time
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Request, status
from opentelemetry import trace

from app.core.database import get_collection
from app.repositories.delivery_intent import DeliveryIntentRepository
from app.shared.celery_app import celery_app
from app.shared.config import settings
from app.shared.metrics import webhook_duration_seconds, webhooks_total
from app.shared.observability import inject_context
from app.shared.recipient import resolve_recipient
from app.shared.schemas.alertmanager import AlertmanagerWebhook
from app.shared.schemas.delivery import (
    Channel,
    DeliveryIntentCreate,
    DeliverySource,
)

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("alert.webhook")
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@lru_cache(maxsize=1)
def _load_webhook_token() -> str:
    path = settings.ALERTMANAGER_WEBHOOK_TOKEN_FILE
    try:
        token = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        logger.error("webhook token file missing at %s", path)
        return ""
    except OSError as exc:
        logger.error("webhook token file unreadable at %s: %s", path, exc)
        return ""
    if not token:
        logger.error("webhook token file empty at %s", path)
    return token


def _reset_token_cache() -> None:
    _load_webhook_token.cache_clear()


async def require_bearer_token(request: Request) -> None:
    expected = _load_webhook_token()
    if not expected:
        webhooks_total.add(1, {"result": "misconfigured"})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="webhook token not configured",
        )
    header = request.headers.get("authorization", "")
    scheme, _, presented = header.partition(" ")
    if scheme.lower() != "bearer" or not presented:
        webhooks_total.add(1, {"result": "unauthorized"})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
        )
    if not secrets.compare_digest(presented, expected):
        webhooks_total.add(1, {"result": "unauthorized"})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid bearer token",
        )


@router.post(
    "/alertmanager",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_bearer_token)],
)
async def receive_alertmanager(payload: AlertmanagerWebhook) -> None:
    start = time.perf_counter()
    try:
        with tracer.start_as_current_span("alertmanager.enqueue") as span:
            span.set_attribute("alertmanager.group_key", payload.group_key)
            span.set_attribute("alertmanager.status", payload.status)
            span.set_attribute("alertmanager.alerts", len(payload.alerts))

            try:
                intent_repo = DeliveryIntentRepository(
                    get_collection(settings.DELIVERY_INTENT_COLLECTION)
                )
                intent = await intent_repo.acquire(
                    DeliveryIntentCreate(
                        source=DeliverySource.ALERTMANAGER,
                        source_ref=payload.group_key,
                        channel=Channel.TELEGRAM,
                        recipient=resolve_recipient(),
                        payload=payload.model_dump(mode="json"),
                        trace_carrier=inject_context(),
                    )
                )
            except Exception as exc:
                logger.error(
                    "intent write failed for alertmanager group=%s: %s",
                    payload.group_key,
                    exc,
                )
                span.set_attribute("alertmanager.persisted", False)
                webhooks_total.add(1, {"result": "persist_failed"})
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="intent write failed",
                ) from exc
            span.set_attribute("alertmanager.persisted", True)
            span.set_attribute("intent.id", intent.id)

            try:
                await asyncio.to_thread(
                    celery_app.send_task,
                    "app.worker.tasks.send_alert_task",
                    args=[intent.id],
                )
            except Exception as exc:
                logger.warning(
                    "enqueue failed group=%s intent=%s: %s, reconciler will retry",
                    payload.group_key,
                    intent.id,
                    exc,
                )
                span.set_attribute("alertmanager.enqueued", False)
            else:
                span.set_attribute("alertmanager.enqueued", True)
                logger.info(
                    "alertmanager webhook accepted group=%s status=%s alerts=%d intent=%s",
                    payload.group_key,
                    payload.status,
                    len(payload.alerts),
                    intent.id,
                )

            webhooks_total.add(1, {"result": "accepted"})
    finally:
        webhook_duration_seconds.record(time.perf_counter() - start)
