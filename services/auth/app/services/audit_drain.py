from __future__ import annotations

import asyncio
import contextlib
import logging
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import grpc
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.database import get_sessionmaker
from app.repositories.audit_outbox_repository import AuditOutboxRepository, PendingEvent
from app.server.grpc_gen import audit_pb2 as pb
from app.services.audit_service import audit_stub

logger = logging.getLogger(__name__)

_BATCH_SIZE = 32
_IDLE_SLEEP_SECONDS = 5.0
_BASE_BACKOFF_SECONDS = 2.0
_MAX_BACKOFF_SECONDS = 300.0
_MAX_BACKOFF_EXPONENT = 8
_MAX_UNKNOWN_STATUS_ATTEMPTS = 12
_TERMINAL_STATUSES = frozenset({pb.APPEND_STATUS_REJECTED, pb.APPEND_STATUS_SCHEMA_UNSUPPORTED})
_jitter_source = random.SystemRandom()


@dataclass(frozen=True, slots=True)
class SendOutcome:
    reachable: bool
    status: int | None


def _next_attempt_at(attempts: int) -> datetime:
    exponent = min(attempts, _MAX_BACKOFF_EXPONENT)
    delay = min(_BASE_BACKOFF_SECONDS * (2**exponent), _MAX_BACKOFF_SECONDS)
    jittered = delay * _jitter_source.uniform(0.8, 1.2)
    return datetime.now(UTC) + timedelta(seconds=jittered)


async def _send(pending: PendingEvent) -> SendOutcome:
    stub = audit_stub()
    if stub is None:
        return SendOutcome(reachable=False, status=None)
    event = pb.AuditEvent()
    event.ParseFromString(pending.event_bytes)
    try:
        reply = await stub.AppendEvent(
            event,
            timeout=get_settings().audit_append_timeout_seconds,
        )
    except grpc.aio.AioRpcError as exc:
        logger.warning("audit append failed code=%s", exc.code().name)
        return SendOutcome(reachable=False, status=None)
    return SendOutcome(reachable=True, status=reply.status)


async def _resolve(
    outbox: AuditOutboxRepository, pending: PendingEvent, outcome: SendOutcome
) -> str:
    if not outcome.reachable:
        await outbox.defer(pending.id, _next_attempt_at(pending.attempts))
        return "deferred"
    if outcome.status == pb.APPEND_STATUS_ACCEPTED:
        await outbox.release(pending.id)
        return "accepted"
    if outcome.status in _TERMINAL_STATUSES:
        await outbox.bury(pending, outcome.status or 0)
        logger.error(
            "audit event rejected, moved to dead letter event_id=%s status=%s",
            pending.event_id,
            outcome.status,
        )
        return "buried"
    if pending.attempts + 1 >= _MAX_UNKNOWN_STATUS_ATTEMPTS:
        await outbox.bury(pending, outcome.status or 0)
        logger.error(
            "audit event moved to dead letter after unrecognised replies event_id=%s status=%s",
            pending.event_id,
            outcome.status,
        )
        return "buried"
    logger.warning(
        "audit append returned unrecognised status=%s event_id=%s",
        outcome.status,
        pending.event_id,
    )
    await outbox.defer(pending.id, _next_attempt_at(pending.attempts))
    return "deferred"


async def _drain_once() -> int:
    factory = get_sessionmaker()
    handled = 0
    for _ in range(_BATCH_SIZE):
        async with factory() as db:
            outbox = AuditOutboxRepository(db)
            claimed = await outbox.claim(1)
            if not claimed:
                await db.rollback()
                return handled
            pending = claimed[0]
            outcome = await _send(pending)
            resolution = await _resolve(outbox, pending, outcome)
            await db.commit()
        handled += 1
        if resolution == "deferred":
            return handled
    return handled


async def run_drain(stop_event: asyncio.Event) -> None:
    logger.info("audit drain started")
    while not stop_event.is_set():
        try:
            handled = await _drain_once()
        except SQLAlchemyError:
            logger.warning("audit drain paused, outbox store unavailable")
            handled = 0
        except Exception:
            logger.exception("audit drain cycle failed")
            handled = 0
        if handled == _BATCH_SIZE:
            continue
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=_IDLE_SLEEP_SECONDS)
    logger.info("audit drain stopped")
