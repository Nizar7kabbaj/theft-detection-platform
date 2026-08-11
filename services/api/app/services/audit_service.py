from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorDatabase
from opentelemetry import trace

from app.core.config import settings
from app.grpc_gen import audit_pb2 as pb
from app.grpc_gen import common_pb2
from app.repositories.audit_outbox_repository import AuditOutboxRepository

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = 1
_ROLE_BY_NAME = {
    "admin": common_pb2.ROLE_ADMIN,
    "operator": common_pb2.ROLE_OPERATOR,
    "viewer": common_pb2.ROLE_VIEWER,
    "ml_engineer": common_pb2.ROLE_ML_ENGINEER,
    "compliance": common_pb2.ROLE_COMPLIANCE,
}


@dataclass(frozen=True, slots=True)
class PreparedEvent:
    event_id: str
    event_bytes: bytes
    occurred_at: datetime


def _current_trace_id() -> str:
    span = trace.get_current_span()
    context = span.get_span_context()
    if not context.is_valid:
        return ""
    return format(context.trace_id, "032x")


def _roles_to_enum(roles: frozenset[str]) -> list[int]:
    return [_ROLE_BY_NAME[name] for name in roles if name in _ROLE_BY_NAME]


def _freeze(event: pb.AuditEvent, occurred_at: datetime) -> PreparedEvent:
    return PreparedEvent(
        event_id=event.event_id,
        event_bytes=event.SerializeToString(),
        occurred_at=occurred_at,
    )


def _new_event(actor: str, severity: int, occurred_at: datetime) -> pb.AuditEvent:
    event = pb.AuditEvent(
        schema_version=_SCHEMA_VERSION,
        event_id=str(uuid.uuid4()),
        source_service=common_pb2.SOURCE_SERVICE_API,
        trace_id=_current_trace_id(),
        actor=actor,
        severity=severity,
    )
    event.occurred_at.FromDatetime(occurred_at)
    return event


def authorization_denied(
    subject_id: str,
    required_permission: str,
    channel: int,
    method: str,
    path: str,
    roles: frozenset[str],
) -> PreparedEvent:
    occurred_at = datetime.now(UTC)
    event = _new_event(subject_id, common_pb2.SEVERITY_WARNING, occurred_at)
    denial = event.authorization_denied
    denial.subject_id = subject_id
    denial.required_permission = required_permission
    denial.channel = channel
    denial.method = method
    denial.path = path
    denial.subject_roles.extend(_roles_to_enum(roles))
    return _freeze(event, occurred_at)


def events_shed(dropped: int) -> PreparedEvent:
    occurred_at = datetime.now(UTC)
    event = _new_event("", common_pb2.SEVERITY_ERROR, occurred_at)
    throttle = event.auth_throttle_triggered
    throttle.bucket = common_pb2.THROTTLE_BUCKET_GLOBAL
    throttle.observed_count = dropped
    throttle.threshold = settings.AUDIT_OUTBOX_MAX_PENDING
    throttle.window_seconds = 0
    return _freeze(event, occurred_at)


class AuditClient:
    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        self._outbox = AuditOutboxRepository(database)

    async def emit_authorization_denied(
        self,
        subject_id: str,
        required_permission: str,
        channel: int,
        method: str,
        path: str,
        roles: frozenset[str],
    ) -> None:
        prepared = authorization_denied(
            subject_id=subject_id,
            required_permission=required_permission,
            channel=channel,
            method=method,
            path=path,
            roles=roles,
        )
        await self._enqueue(prepared)

    async def _enqueue(self, prepared: PreparedEvent) -> None:
        try:
            pending = await self._outbox.pending_count()
            if pending >= settings.AUDIT_OUTBOX_MAX_PENDING:
                await self._shed()
                return
            await self._outbox.enqueue(
                prepared.event_id, prepared.event_bytes, prepared.occurred_at
            )
        except Exception:
            logger.error("audit event lost, outbox write failed event_id=%s", prepared.event_id)

    async def _shed(self) -> None:
        marker = events_shed(1)
        try:
            await self._outbox.enqueue(marker.event_id, marker.event_bytes, marker.occurred_at)
        except Exception:
            logger.error("audit shed marker lost, outbox write failed")
