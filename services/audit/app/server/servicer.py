from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

import grpc
from google.protobuf.message import DecodeError
from google.protobuf.timestamp_pb2 import Timestamp
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.chain import DEFAULT_HASH_ALGORITHM, is_supported
from app.core.config import get_settings
from app.core.database import get_sessionmaker
from app.core.pseudonym import PseudonymKeyError, pseudonymize
from app.core.redis import check_append_rate
from app.repositories.audit_repository import (
    VERIFY_FAILURE_NONE,
    AuditRepository,
)
from app.server.grpc_gen import audit_pb2, audit_pb2_grpc, common_pb2
from app.server.interceptors import peer_service
from app.services.checkpoint_service import verify_checkpoints

logger = logging.getLogger(__name__)

_MAX_PAGE_SIZE = 500
_DEFAULT_PAGE_SIZE = 100
_ACTOR_DOMAIN = "audit-query-actor"

_PAYLOAD_FIELD_NUMBERS = {
    field.name: field.number
    for field in audit_pb2.AuditEvent.DESCRIPTOR.oneofs_by_name["payload"].fields
}


def _to_datetime(message, field: str) -> datetime | None:
    if not message.HasField(field):
        return None
    return getattr(message, field).ToDatetime(tzinfo=UTC)


def _to_timestamp(value: datetime) -> Timestamp:
    ts = Timestamp()
    ts.FromDatetime(value)
    return ts


def _parse_sequence(raw: str) -> tuple[int | None, bool]:
    if not raw:
        return None, True
    try:
        value = int(raw)
    except ValueError:
        return None, False
    if value < 0:
        return None, False
    return value, True


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return True


def _payload_kind(request: audit_pb2.AuditEvent) -> int:
    field = request.WhichOneof("payload")
    if field is None:
        return 0
    return _PAYLOAD_FIELD_NUMBERS.get(field, 0)


def _clock_within_bounds(occurred_at: datetime) -> bool:
    settings = get_settings()
    now = datetime.now(UTC)
    if occurred_at > now + timedelta(seconds=settings.max_clock_skew_seconds):
        return False
    return occurred_at >= now - timedelta(seconds=settings.max_backdate_seconds)


def _rejected() -> audit_pb2.AppendEventReply:
    return audit_pb2.AppendEventReply(status=audit_pb2.APPEND_STATUS_REJECTED)


class AuditServicer(audit_pb2_grpc.AuditServiceServicer):
    async def AppendEvent(
        self,
        request: audit_pb2.AuditEvent,
        context: grpc.aio.ServicerContext,
    ) -> audit_pb2.AppendEventReply:
        settings = get_settings()
        if int(request.source_service) != peer_service():
            logger.warning("source_service does not match caller certificate")
            return _rejected()
        if not _is_uuid(request.event_id):
            return _rejected()
        schema_version = request.schema_version or settings.schema_version
        if (
            schema_version < settings.min_accepted_schema_version
            or schema_version > settings.schema_version
        ):
            return audit_pb2.AppendEventReply(status=audit_pb2.APPEND_STATUS_SCHEMA_UNSUPPORTED)
        occurred_at = _to_datetime(request, "occurred_at")
        if occurred_at is None or not _clock_within_bounds(occurred_at):
            return _rejected()
        payload_kind = _payload_kind(request)
        if payload_kind == 0:
            return _rejected()

        if not is_supported(DEFAULT_HASH_ALGORITHM):
            return _rejected()

        allowed = await check_append_rate(int(request.source_service))
        if not allowed:
            return audit_pb2.AppendEventReply(status=audit_pb2.APPEND_STATUS_RATE_LIMITED)

        event_bytes = request.SerializeToString(deterministic=True)
        factory = get_sessionmaker()
        try:
            async with factory() as db:
                result = await AuditRepository(db).append(
                    event_id=request.event_id,
                    occurred_at=occurred_at,
                    source_service=int(request.source_service),
                    actor=request.actor,
                    severity=int(request.severity),
                    trace_id=request.trace_id,
                    payload_kind=payload_kind,
                    schema_version=schema_version,
                    event_bytes=event_bytes,
                )
                await db.commit()
        except IntegrityError:
            logger.warning("append rejected by constraint")
            return _rejected()
        except SQLAlchemyError:
            logger.warning("audit store unavailable during append")
            await context.abort(grpc.StatusCode.UNAVAILABLE, "audit store unavailable")
        return audit_pb2.AppendEventReply(
            status=audit_pb2.APPEND_STATUS_ACCEPTED,
            sequence_number=str(result.sequence_number),
            chain_hash=result.chain_hash,
            leaf_hash=result.leaf_hash,
            persisted_at=_to_timestamp(result.persisted_at),
        )

    async def _record_access(
        self,
        db,
        scope: int,
        rows_returned: int,
        from_time: datetime | None,
        to_time: datetime | None,
        source_service: int,
        actor: str,
        min_severity: int,
    ) -> None:
        event = audit_pb2.AuditEvent()
        event.schema_version = get_settings().schema_version
        event.event_id = str(uuid.uuid4())
        event.occurred_at.FromDatetime(datetime.now(UTC))
        event.source_service = common_pb2.SOURCE_SERVICE_AUDIT
        event.severity = common_pb2.SEVERITY_INFO
        access = event.audit_log_accessed
        access.scope = scope
        access.rows_returned = rows_returned
        if from_time is not None:
            access.window_from.FromDatetime(from_time)
        if to_time is not None:
            access.window_to.FromDatetime(to_time)
        if source_service > 0:
            access.filter_source_service = source_service
        if min_severity > 0:
            access.filter_min_severity = min_severity
        if actor:
            try:
                access.filter_actor_hmac = pseudonymize(_ACTOR_DOMAIN, actor)
            except PseudonymKeyError:
                logger.error("pseudonym key unavailable, access record refused")
                raise
        await AuditRepository(db).append(
            event_id=event.event_id,
            occurred_at=event.occurred_at.ToDatetime(tzinfo=UTC),
            source_service=common_pb2.SOURCE_SERVICE_AUDIT,
            actor="",
            severity=common_pb2.SEVERITY_INFO,
            trace_id="",
            payload_kind=_PAYLOAD_FIELD_NUMBERS["audit_log_accessed"],
            schema_version=event.schema_version,
            event_bytes=event.SerializeToString(deterministic=True),
        )

    async def QueryEvents(
        self,
        request: audit_pb2.QueryEventsRequest,
        context: grpc.aio.ServicerContext,
    ) -> audit_pb2.QueryEventsReply:
        page_size = request.page_size or _DEFAULT_PAGE_SIZE
        page_size = min(page_size, _MAX_PAGE_SIZE)
        if page_size < 1:
            page_size = _DEFAULT_PAGE_SIZE
        after, ok = _parse_sequence(request.page_token)
        if not ok:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "malformed page token")
        from_time = _to_datetime(request, "from_time")
        to_time = _to_datetime(request, "to_time")
        factory = get_sessionmaker()
        try:
            async with factory() as db:
                events = AuditRepository(db)
                rows = await events.query(
                    from_time=from_time,
                    to_time=to_time,
                    source_service=int(request.source_service),
                    actor=request.actor,
                    min_severity=int(request.min_severity),
                    page_size=page_size,
                    after_sequence_number=after,
                )
                await self._record_access(
                    db,
                    audit_pb2.AUDIT_QUERY_SCOPE_EVENTS,
                    len(rows),
                    from_time,
                    to_time,
                    int(request.source_service),
                    request.actor,
                    int(request.min_severity),
                )
                await db.commit()
        except SQLAlchemyError:
            logger.warning("audit store unavailable during query")
            await context.abort(grpc.StatusCode.UNAVAILABLE, "audit store unavailable")
        except PseudonymKeyError:
            await context.abort(
                grpc.StatusCode.FAILED_PRECONDITION, "access record cannot be written"
            )
        stored = []
        for row in rows:
            entry = audit_pb2.StoredAuditEvent(
                sequence_number=str(row.sequence_number),
                chain_hash=row.chain_hash,
                leaf_hash=row.leaf_hash,
                persisted_at=_to_timestamp(row.persisted_at),
                erased=row.erased_at is not None,
            )
            if row.erased_at is not None:
                entry.erased_at.CopyFrom(_to_timestamp(row.erased_at))
            elif row.event_bytes is not None:
                try:
                    entry.event.ParseFromString(row.event_bytes)
                except DecodeError:
                    logger.warning(
                        "stored payload not parseable at sequence %s",
                        row.sequence_number,
                    )
                    entry.ClearField("event")
            stored.append(entry)
        next_page_token = ""
        if len(rows) == page_size and rows:
            next_page_token = str(rows[-1].sequence_number)
        return audit_pb2.QueryEventsReply(events=stored, next_page_token=next_page_token)

    async def VerifyChain(
        self,
        request: audit_pb2.VerifyChainRequest,
        context: grpc.aio.ServicerContext,
    ) -> audit_pb2.VerifyChainReply:
        start, ok_start = _parse_sequence(request.from_sequence_number)
        end, ok_end = _parse_sequence(request.to_sequence_number)
        if not ok_start or not ok_end:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "malformed sequence range")
        factory = get_sessionmaker()
        try:
            async with factory() as db:
                events = AuditRepository(db)
                checkpoints = await verify_checkpoints(events)
                result = await events.verify(from_sequence_number=start, to_sequence_number=end)
                await self._record_access(
                    db,
                    audit_pb2.AUDIT_QUERY_SCOPE_VERIFY,
                    result.events_verified,
                    None,
                    None,
                    0,
                    "",
                    0,
                )
                await db.commit()
        except SQLAlchemyError:
            logger.warning("audit store unavailable during verify")
            await context.abort(grpc.StatusCode.UNAVAILABLE, "audit store unavailable")
        intact = result.chain_intact and checkpoints.failure_kind == VERIFY_FAILURE_NONE
        failure_kind = result.failure_kind
        break_at = ""
        if result.break_at_sequence_number is not None:
            break_at = str(result.break_at_sequence_number)
        if result.chain_intact and checkpoints.failure_kind != VERIFY_FAILURE_NONE:
            failure_kind = checkpoints.failure_kind
        return audit_pb2.VerifyChainReply(
            chain_intact=intact,
            break_at_sequence_number=break_at,
            failure_kind=failure_kind,
            events_verified=result.events_verified,
            erased_rows_verified=result.erased_rows_verified,
            checkpoints_verified=checkpoints.checkpoints_verified,
        )

    async def GetCheckpoint(
        self,
        request: audit_pb2.GetCheckpointRequest,
        context: grpc.aio.ServicerContext,
    ) -> audit_pb2.GetCheckpointReply:
        factory = get_sessionmaker()
        try:
            async with factory() as db:
                events = AuditRepository(db)
                if request.checkpoint_id > 0:
                    row = await events.checkpoint_by_id(request.checkpoint_id)
                else:
                    row = await events.latest_checkpoint()
                await self._record_access(
                    db,
                    audit_pb2.AUDIT_QUERY_SCOPE_CHECKPOINT,
                    1 if row is not None else 0,
                    None,
                    None,
                    0,
                    "",
                    0,
                )
                await db.commit()
        except SQLAlchemyError:
            logger.warning("audit store unavailable during checkpoint read")
            await context.abort(grpc.StatusCode.UNAVAILABLE, "audit store unavailable")
        if row is None:
            return audit_pb2.GetCheckpointReply(found=False)
        return audit_pb2.GetCheckpointReply(
            found=True,
            checkpoint=audit_pb2.Checkpoint(
                checkpoint_id=row.checkpoint_id,
                tail_sequence_number=str(row.tail_sequence_number),
                tail_chain_hash=row.tail_chain_hash,
                tree_size=row.tree_size,
                hash_algorithm=row.hash_algorithm,
                signature_algorithm=row.signature_algorithm,
                signature=row.signature,
                key_id=row.key_id,
                signed_at=_to_timestamp(row.signed_at),
                prev_checkpoint_hash=row.prev_checkpoint_hash,
                checkpoint_hash=row.checkpoint_hash,
            ),
        )

    async def ErasePayloads(
        self,
        request: audit_pb2.ErasePayloadsRequest,
        context: grpc.aio.ServicerContext,
    ) -> audit_pb2.ErasePayloadsReply:
        if peer_service() != common_pb2.SOURCE_SERVICE_AUTH:
            await context.abort(grpc.StatusCode.PERMISSION_DENIED, "erasure caller not permitted")
        if not request.subject_id or not request.requested_by:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "subject and requester required")
        if request.reason == audit_pb2.ERASURE_REASON_UNSPECIFIED:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "erasure reason required")
        factory = get_sessionmaker()
        try:
            async with factory() as db:
                erased = await AuditRepository(db).erase_subject_payloads(
                    request.subject_id,
                    int(request.reason),
                )
                await db.commit()
        except SQLAlchemyError:
            logger.warning("audit store unavailable during erasure")
            await context.abort(grpc.StatusCode.UNAVAILABLE, "audit store unavailable")
        logger.info("erased %d audit payloads on subject request", erased)
        return audit_pb2.ErasePayloadsReply(records_erased=erased, completed=True)
