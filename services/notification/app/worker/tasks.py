from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from opentelemetry import trace
from opentelemetry.trace import Link
from pydantic import ValidationError

from app.core.database import (
    close_mongodb_connection,
    connect_to_mongodb,
    get_collection,
)
from app.repositories.dead_letter import DeadLetterRepository
from app.repositories.delivery_intent import DeliveryIntentRepository
from app.shared import gate
from app.shared.celery_app import celery_app
from app.shared.config import settings
from app.shared.decision_token import decision_keyboard
from app.shared.metrics import telegram_messages_total
from app.shared.observability import extract_context
from app.shared.recipient import UNCONFIGURED_RECIPIENT
from app.shared.schemas.delivery import (
    DeadLetterCreate,
    DeliveryIntent,
    DeliverySource,
    DeliveryStatus,
    TelegramMessageRef,
)
from app.shared.telegram_service import (
    MessageKind,
    SentMessage,
    TelegramError,
    TelegramPermanentError,
    TelegramTransientError,
    TelegramUnreachableError,
    clip_missing,
    edit_message,
    open_client,
    prefer_annotated,
    probe,
    send_message,
    send_photo,
    send_video,
)
from app.worker.renderers import DECISION_PROMPT, render, render_decision_outcome

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("notification.worker")


def _keyboard_for(intent: DeliveryIntent) -> dict[str, Any] | None:
    if intent.source != DeliverySource.ALERT:
        return None
    try:
        return decision_keyboard(intent.id)
    except (OSError, RuntimeError, ValueError) as exc:
        logger.error("intent %s decision buttons unavailable: %s", intent.id, exc)
        telegram_messages_total.add(1, {"method": "keyboard", "result": "unavailable"})
        return None


def _compose(base: str, block: str) -> str:
    return f"{base}\n\n{block}" if base else block


async def _send_snapshot(
    client: httpx.AsyncClient,
    intent: DeliveryIntent,
    intent_repo: DeliveryIntentRepository,
    cover: str,
    text: str,
) -> bool:
    if intent.telegram_snapshot is not None:
        return True
    snapshot = await send_photo(client, cover, text)
    if snapshot is None:
        return False
    await intent_repo.mark_snapshot_sent(
        intent.id,
        TelegramMessageRef(
            chat_id=snapshot.chat_id, message_id=snapshot.message_id, kind=snapshot.kind.value
        ),
    )
    return True


async def _send_plain(
    client: httpx.AsyncClient, text: str, cover: str | None, clip_path: str | None
) -> SentMessage | None:
    if clip_path:
        sent = await send_video(client, clip_path, cover, text)
        if sent is not None:
            return sent
    if cover:
        sent = await send_photo(client, cover, text)
        if sent is not None:
            return sent
    return await send_message(client, text)


async def _dispatch(
    intent: DeliveryIntent,
    intent_repo: DeliveryIntentRepository,
    text: str,
    photo_path: str | None,
    clip_path: str | None,
) -> SentMessage | None:
    keyboard = _keyboard_for(intent)
    cover = prefer_annotated(photo_path) if photo_path else None
    async with open_client() as client:
        if keyboard is None:
            return await _send_plain(client, text, cover, clip_path)
        has_snapshot = cover is not None and await _send_snapshot(
            client, intent, intent_repo, cover, text
        )
        prompt = DECISION_PROMPT if has_snapshot else _compose(text, DECISION_PROMPT)
        if clip_path:
            sent = await send_video(client, clip_path, cover, prompt, reply_markup=keyboard)
            if sent is not None:
                return sent
        return await send_message(client, prompt, reply_markup=keyboard)


async def _await_clip(clip_path: str) -> bool:
    deadline = asyncio.get_running_loop().time() + settings.CLIP_WAIT_SEC
    while clip_missing(clip_path):
        if asyncio.get_running_loop().time() >= deadline:
            return False
        await asyncio.sleep(settings.CLIP_POLL_INTERVAL_SEC)
    return True


async def _require_clip(
    intent_id: str,
    clip_path: str | None,
    final_attempt: bool,
    intent_repo: DeliveryIntentRepository,
) -> None:
    if not clip_path or not clip_missing(clip_path):
        return
    if await _await_clip(clip_path):
        logger.info("intent %s clip ready after wait", intent_id)
        return
    if final_attempt:
        logger.warning("intent %s sending without clip", intent_id)
        return
    error = "clip not written yet"
    await intent_repo.mark_failed(intent_id, error)
    logger.info("intent %s waiting on clip, will retry", intent_id)
    raise TelegramTransientError(error)


async def _deliver(intent_id: str, final_attempt: bool) -> dict[str, Any]:
    await connect_to_mongodb()
    try:
        intent_repo = DeliveryIntentRepository(get_collection(settings.DELIVERY_INTENT_COLLECTION))
        dlq_repo = DeadLetterRepository(get_collection(settings.DEAD_LETTER_COLLECTION))
        intent = await intent_repo.get_by_id(intent_id)
        if intent is None:
            logger.error("intent %s not found, dropping", intent_id)
            return {"intent_id": intent_id, "delivered": False, "reason": "missing"}
        if intent.status == DeliveryStatus.SENT:
            logger.info("intent %s already sent, skipping", intent_id)
            return {"intent_id": intent_id, "delivered": True, "reason": "already_sent"}
        if intent.recipient == UNCONFIGURED_RECIPIENT:
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
            logger.error("intent %s dead, telegram not configured", intent_id)
            return {"intent_id": intent_id, "delivered": False, "reason": "unconfigured"}
        if gate.gate_is_raised():
            await intent_repo.mark_buffered(intent.id, "telegram gate raised")
            logger.info("intent %s buffered, gate raised", intent_id)
            return {"intent_id": intent_id, "delivered": False, "reason": "gate_buffered"}

        claimed = await intent_repo.mark_sending(intent.id)
        if claimed is None:
            logger.info("intent %s claimed elsewhere, skipping", intent_id)
            return {"intent_id": intent_id, "delivered": False, "reason": "not_claimed"}
        try:
            text, photo_path, clip_path = render(intent.source, intent.payload)
        except (ValidationError, ValueError) as exc:
            error = f"render failed: {exc}"
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
            logger.error("intent %s dead, %s", intent_id, error)
            return {"intent_id": intent_id, "delivered": False, "reason": "render"}
        try:
            await _require_clip(intent_id, clip_path, final_attempt, intent_repo)
            sent = await _dispatch(intent, intent_repo, text, photo_path, clip_path)
        except TelegramUnreachableError as exc:
            error = str(exc)
            gate.gate_set(error)
            await intent_repo.mark_buffered(intent.id, error)
            logger.warning("intent %s buffered, telegram unreachable: %s", intent_id, error)
            return {"intent_id": intent_id, "delivered": False, "reason": "buffered"}
        except TelegramPermanentError as exc:
            error = str(exc)
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
            logger.error("intent %s dead, permanent: %s", intent_id, error)
            return {"intent_id": intent_id, "delivered": False, "reason": "permanent"}
        except TelegramError as exc:
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
                logger.error("intent %s dead after retries: %s", intent_id, error)
                return {"intent_id": intent_id, "delivered": False, "reason": "dead"}
            await intent_repo.mark_failed(intent.id, error)
            logger.warning("intent %s failed, will retry: %s", intent_id, error)
            raise
        if sent is None:
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
            logger.error("intent %s dead, telegram declined", intent_id)
            return {"intent_id": intent_id, "delivered": False, "reason": "declined"}
        await intent_repo.mark_sent(
            intent.id,
            TelegramMessageRef(
                chat_id=sent.chat_id, message_id=sent.message_id, kind=sent.kind.value
            ),
        )
        logger.info("intent %s delivered message=%d", intent_id, sent.message_id)
        return {"intent_id": intent_id, "delivered": True}
    finally:
        await close_mongodb_connection()


@celery_app.task(
    name="app.worker.tasks.send_alert_task",
    bind=True,
    max_retries=settings.CELERY_TASK_MAX_RETRIES,
    default_retry_delay=settings.CELERY_TASK_RETRY_DELAY_SEC,
    autoretry_for=(TelegramTransientError, TelegramUnreachableError),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    acks_late=True,
)
def send_alert_task(self, intent_id: str) -> dict[str, Any]:
    final_attempt = self.request.retries >= self.max_retries
    logger.info("delivering intent %s attempt=%d", intent_id, self.request.retries + 1)
    return asyncio.run(_deliver(intent_id, final_attempt))


async def _retire_poison(
    intent: DeliveryIntent,
    intent_repo: DeliveryIntentRepository,
    dlq_repo: DeadLetterRepository,
) -> None:
    reason = f"exceeded {settings.RECONCILER_MAX_REQUEUES} requeues"
    await intent_repo.mark_dead(intent.id, reason)
    await dlq_repo.create(
        DeadLetterCreate(
            source=intent.source,
            source_ref=intent.source_ref,
            channel=intent.channel,
            recipient=intent.recipient,
            payload=intent.payload,
            trace_carrier=intent.trace_carrier,
            attempts=intent.attempts,
            last_error=reason,
            intent_id=intent.id,
        )
    )
    logger.error("intent %s dead, %s", intent.id, reason)


async def _requeue_one(
    intent: DeliveryIntent,
    cutoff: datetime,
    intent_repo: DeliveryIntentRepository,
    dlq_repo: DeadLetterRepository,
    sweep_span: trace.Span,
) -> str:
    if intent.requeue_count >= settings.RECONCILER_MAX_REQUEUES:
        await _retire_poison(intent, intent_repo, dlq_repo)
        return "poison"
    requeued = await intent_repo.mark_requeued(intent.id, cutoff)
    if requeued is None:
        return "raced"
    ctx = extract_context(intent.trace_carrier)
    link = Link(sweep_span.get_span_context())
    with tracer.start_as_current_span("reconcile_requeue", context=ctx, links=[link]) as span:
        span.set_attribute("intent.id", intent.id)
        span.set_attribute("intent.source_ref", intent.source_ref)
        span.set_attribute("intent.requeue_count", requeued.requeue_count)
        send_alert_task.apply_async(args=[intent.id])
    logger.info("intent %s requeued count=%d", intent.id, requeued.requeue_count)
    return "requeued"


async def _reconcile() -> dict[str, int]:
    await connect_to_mongodb()
    try:
        intent_repo = DeliveryIntentRepository(get_collection(settings.DELIVERY_INTENT_COLLECTION))
        dlq_repo = DeadLetterRepository(get_collection(settings.DEAD_LETTER_COLLECTION))
        now = datetime.now(UTC)
        sending_cutoff = now - timedelta(seconds=settings.DELIVERY_INTENT_SENDING_TIMEOUT_SEC)
        pending_cutoff = now - timedelta(seconds=settings.DELIVERY_INTENT_PENDING_TIMEOUT_SEC)
        stale = await intent_repo.find_stale(DeliveryStatus.SENDING, sending_cutoff)
        stale += await intent_repo.find_stale(DeliveryStatus.PENDING, pending_cutoff)
        tally = {"requeued": 0, "poison": 0, "raced": 0}
        if not stale:
            return tally
        with tracer.start_as_current_span("reconcile_sweep") as sweep_span:
            sweep_span.set_attribute("stale.count", len(stale))
            for intent in stale:
                cutoff = (
                    sending_cutoff if intent.status == DeliveryStatus.SENDING else pending_cutoff
                )
                outcome = await _requeue_one(intent, cutoff, intent_repo, dlq_repo, sweep_span)
                tally[outcome] += 1
            sweep_span.set_attribute("reconcile.requeued", tally["requeued"])
            sweep_span.set_attribute("reconcile.poison", tally["poison"])
            sweep_span.set_attribute("reconcile.raced", tally["raced"])
        logger.info(
            "reconcile swept=%d requeued=%d poison=%d raced=%d",
            len(stale),
            tally["requeued"],
            tally["poison"],
            tally["raced"],
        )
        return tally
    finally:
        await close_mongodb_connection()


@celery_app.task(name="app.worker.tasks.reconcile_intents_task")
def reconcile_intents_task() -> dict[str, int]:
    if not settings.RECONCILER_ENABLED:
        return {"requeued": 0, "poison": 0, "raced": 0}
    return asyncio.run(_reconcile())


async def _drain_buffer() -> dict[str, int]:
    await connect_to_mongodb()
    try:
        intent_repo = DeliveryIntentRepository(get_collection(settings.DELIVERY_INTENT_COLLECTION))
        released = await intent_repo.release_buffered(settings.GATE_DRAIN_BATCH)
        for intent in released:
            ctx = extract_context(intent.trace_carrier)
            with tracer.start_as_current_span("drain_release", context=ctx) as span:
                span.set_attribute("intent.id", intent.id)
                span.set_attribute("intent.source_ref", intent.source_ref)
                send_alert_task.apply_async(args=[intent.id])
        logger.info("drain released=%d", len(released))
        return {"released": len(released)}
    finally:
        await close_mongodb_connection()


_UNDECIDED = "DECISION_UNSPECIFIED"


async def _show_decision(
    client: httpx.AsyncClient,
    intent: DeliveryIntent,
    intent_repo: DeliveryIntentRepository,
    decision: str,
    decided_by: str,
    decided_at: datetime,
) -> str:
    ref = intent.telegram
    if ref is None:
        return "skipped"
    if not await intent_repo.claim_display(intent.id, decided_at):
        return "stale"
    text, _, _ = render(intent.source, intent.payload)
    base = "" if intent.telegram_snapshot is not None else text
    if decision == _UNDECIDED:
        markup = _keyboard_for(intent)
        body = _compose(base, DECISION_PROMPT) if markup is not None else (base or text)
    else:
        markup = None
        body = _compose(base, render_decision_outcome(decision, decided_by, decided_at))
    try:
        await edit_message(client, ref.chat_id, ref.message_id, MessageKind(ref.kind), body, markup)
    except TelegramPermanentError as exc:
        logger.warning("intent %s decision not shown: %s", intent.id, exc)
        return "failed"
    return "edited"


async def _apply_decision(
    alert_id: str, decision: str, decided_by: str, decided_at: datetime
) -> dict[str, int]:
    await connect_to_mongodb()
    try:
        intent_repo = DeliveryIntentRepository(get_collection(settings.DELIVERY_INTENT_COLLECTION))
        intents = await intent_repo.list_by_source_ref(DeliverySource.ALERT, alert_id)
        tally = {"edited": 0, "stale": 0, "failed": 0, "skipped": 0}
        if not intents:
            return tally
        async with open_client() as client:
            for intent in intents:
                outcome = await _show_decision(
                    client, intent, intent_repo, decision, decided_by, decided_at
                )
                tally[outcome] += 1
        logger.info(
            "decision shown alert=%s edited=%d stale=%d failed=%d",
            alert_id,
            tally["edited"],
            tally["stale"],
            tally["failed"],
        )
        return tally
    finally:
        await close_mongodb_connection()


@celery_app.task(
    name="app.worker.tasks.apply_decision_task",
    max_retries=settings.CELERY_TASK_MAX_RETRIES,
    default_retry_delay=settings.CELERY_TASK_RETRY_DELAY_SEC,
    autoretry_for=(TelegramTransientError, TelegramUnreachableError),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    acks_late=True,
)
def apply_decision_task(
    alert_id: str, decision: str, decided_by: str, decided_at: str
) -> dict[str, int]:
    return asyncio.run(
        _apply_decision(alert_id, decision, decided_by, datetime.fromisoformat(decided_at))
    )


async def _probe_telegram() -> bool:
    async with open_client() as client:
        return await probe(client)


@celery_app.task(name="app.worker.tasks.probe_gate_task")
def probe_gate_task() -> dict[str, int]:
    if not gate.gate_is_raised():
        return {"released": 0, "probed": 0}
    if not asyncio.run(_probe_telegram()):
        gate.gate_refresh()
        logger.info("gate probe: telegram still unreachable, gate refreshed")
        return {"released": 0, "probed": 1}
    gate.gate_clear()
    return asyncio.run(_drain_buffer()) | {"probed": 1}
