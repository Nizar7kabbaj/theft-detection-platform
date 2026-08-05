from __future__ import annotations

import logging
from datetime import datetime, timezone

import grpc
from google.protobuf.timestamp_pb2 import Timestamp
from redis.exceptions import RedisError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.database import get_sessionmaker
from app.core.redis import check_append_rate
from app.repositories.audit_repository import AuditRepository
from app.server.grpc_gen import audit_pb2, audit_pb2_grpc

logger = logging.getLogger(__name__)

_MAX_PAGE_SIZE = 500
_DEFAULT_PAGE_SIZE = 100


def _to_datetime(ts: Timestamp) -> datetime | None:
    if ts.seconds == 0 and ts.nanos == 0:
        return None
    return ts.ToDatetime(tzinfo=timezone.utc)


def _to_timestamp(value: datetime) -> Timestamp:
    ts = Timestamp()
    ts.FromDatetime(value)
    return ts


def _parse_sequence(raw: str) -> int | None:
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


class AuditServicer(audit_pb2_grpc.AuditServiceServicer):
    async def AppendEvent(
        self,
        request: audit_pb2.AuditEvent,
        context: grpc.aio.ServicerContext,
    ) -> audit_pb2.AppendEventReply:
        if not request.event_id:
            return audit_pb2.AppendEventReply(
                status=audit_pb2.APPEND_STATUS_REJECTED
            )

        occurred_at = _to_datetime(request.occurred_at)
        if occurred_at is None:
            return audit_pb2.AppendEventReply(
                status=audit_pb2.APPEND_STATUS_REJECTED
            )

        try:
            allowed = await check_append_rate(request.source_service)
        except RedisError:
            allowed = True
        if not allowed:
            return audit_pb2.AppendEventReply(
                status=audit_pb2.APPEND_STATUS_RATE_LIMITED
            )

        event_bytes = request.SerializeToString(deterministic=True)

        factory = get_sessionmaker()
        try:
            async with factory() as db:
                events = AuditRepository(db)
                result = await events.append(
                    event_id=request.event_id,
                    occurred_at=occurred_at,
                    source_service=request.source_service,
                    actor=request.actor,
                    severity=int(request.severity),
                    trace_id=request.trace_id,
                    event_bytes=event_bytes,
                )
                await db.commit()
        except IntegrityError:
            logger.warning("append rejected by constraint, event_id=%s", request.event_id)
            return audit_pb2.AppendEventReply(
                status=audit_pb2.APPEND_STATUS_REJECTED
            )
        except SQLAlchemyError:
            logger.warning("audit store unavailable, event_id=%s", request.event_id)
            await context.abort(grpc.StatusCode.UNAVAILABLE, "audit store unavailable")

        return audit_pb2.AppendEventReply(
            status=audit_pb2.APPEND_STATUS_ACCEPTED,
            sequence_number=str(result.sequence_number),
            chain_hash=result.chain_hash.hex(),
            persisted_at=_to_timestamp(result.persisted_at),
        )

    async def QueryEvents(
        self,
        request: audit_pb2.QueryEventsRequest,
        context: grpc.aio.ServicerContext,
    ) -> audit_pb2.QueryEventsReply:
        page_size = request.page_size or _DEFAULT_PAGE_SIZE
        if page_size > _MAX_PAGE_SIZE:
            page_size = _MAX_PAGE_SIZE
        if page_size < 1:
            page_size = _DEFAULT_PAGE_SIZE

        factory = get_sessionmaker()
        try:
            async with factory() as db:
                events = AuditRepository(db)
                rows = await events.query(
                    from_time=_to_datetime(request.from_time),
                    to_time=_to_datetime(request.to_time),
                    source_service=request.source_service,
                    actor=request.actor,
                    min_severity=int(request.min_severity),
                    page_size=page_size,
                    after_sequence_number=_parse_sequence(request.page_token),
                )
        except SQLAlchemyError:
            logger.warning("audit store unavailable during query")
            await context.abort(grpc.StatusCode.UNAVAILABLE, "audit store unavailable")

        stored = []
        for row in rows:
            event = audit_pb2.AuditEvent()
            event.ParseFromString(row.event_bytes)
            stored.append(
                audit_pb2.StoredAuditEvent(
                    event=event,
                    sequence_number=str(row.sequence_number),
                    chain_hash=row.chain_hash.hex(),
                    persisted_at=_to_timestamp(row.persisted_at),
                )
            )

        next_page_token = ""
        if len(rows) == page_size:
            next_page_token = str(rows[-1].sequence_number)

        return audit_pb2.QueryEventsReply(
            events=stored, next_page_token=next_page_token
        )

    async def VerifyChain(
        self,
        request: audit_pb2.VerifyChainRequest,
        context: grpc.aio.ServicerContext,
    ) -> audit_pb2.VerifyChainReply:
        factory = get_sessionmaker()
        try:
            async with factory() as db:
                events = AuditRepository(db)
                result = await events.verify(
                    from_sequence_number=_parse_sequence(request.from_sequence_number),
                    to_sequence_number=_parse_sequence(request.to_sequence_number),
                )
        except SQLAlchemyError:
            logger.warning("audit store unavailable during verify")
            await context.abort(grpc.StatusCode.UNAVAILABLE, "audit store unavailable")

        break_at = ""
        if result.break_at_sequence_number is not None:
            break_at = str(result.break_at_sequence_number)

        return audit_pb2.VerifyChainReply(
            chain_intact=result.chain_intact,
            break_at_sequence_number=break_at,
            events_verified=result.events_verified,
        )

    async def Check(self, request, context):
        return None
