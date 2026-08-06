from __future__ import annotations
import asyncio
import logging
import uuid
from datetime import UTC, datetime
import grpc
from opentelemetry import trace
from app.core.config import settings
from app.grpc_gen import audit_pb2 as pb
from app.grpc_gen import common_pb2
from app.grpc_gen.audit_pb2_grpc import AuditServiceStub
logger = logging.getLogger(__name__)
_SCHEMA_VERSION = 1
_MAX_INFLIGHT_APPENDS = 256
_DRAIN_TIMEOUT_SECONDS = 3.0
_ROLE_BY_NAME = {
    "admin": common_pb2.ROLE_ADMIN,
    "operator": common_pb2.ROLE_OPERATOR,
    "viewer": common_pb2.ROLE_VIEWER,
    "ml_engineer": common_pb2.ROLE_ML_ENGINEER,
    "compliance": common_pb2.ROLE_COMPLIANCE,
}
_live_tasks: set[asyncio.Task[None]] = set()
def _current_trace_id() -> str:
    span = trace.get_current_span()
    context = span.get_span_context()
    if not context.is_valid:
        return ""
    return format(context.trace_id, "032x")
def _roles_to_enum(roles: frozenset[str]) -> list[int]:
    return [_ROLE_BY_NAME[name] for name in roles if name in _ROLE_BY_NAME]
async def drain_pending_appends() -> None:
    if not _live_tasks:
        return
    pending = tuple(_live_tasks)
    done, still_running = await asyncio.wait(
        pending, timeout=_DRAIN_TIMEOUT_SECONDS
    )
    if still_running:
        logger.warning("audit appends abandoned at shutdown count=%d", len(still_running))
class AuditClient:
    def __init__(self, stub: AuditServiceStub) -> None:
        self._stub = stub
    def emit_authorization_denied(
        self,
        subject_id: str,
        required_permission: str,
        channel: int,
        method: str,
        path: str,
        roles: frozenset[str],
    ) -> None:
        event = pb.AuditEvent(
            schema_version=_SCHEMA_VERSION,
            event_id=str(uuid.uuid4()),
            source_service=common_pb2.SOURCE_SERVICE_API,
            trace_id=_current_trace_id(),
            actor=subject_id,
            severity=common_pb2.SEVERITY_WARNING,
        )
        event.occurred_at.FromDatetime(datetime.now(UTC))
        denial = event.authorization_denied
        denial.subject_id = subject_id
        denial.required_permission = required_permission
        denial.channel = channel
        denial.method = method
        denial.path = path
        denial.subject_roles.extend(_roles_to_enum(roles))
        self._schedule(event)
    def _schedule(self, event: pb.AuditEvent) -> None:
        if len(_live_tasks) >= _MAX_INFLIGHT_APPENDS:
            logger.warning("audit append shed, in-flight limit reached")
            return
        try:
            task = asyncio.create_task(self._append(event))
        except RuntimeError:
            logger.warning("audit append not scheduled, no running loop")
            return
        _live_tasks.add(task)
        task.add_done_callback(_live_tasks.discard)
    async def _append(self, event: pb.AuditEvent) -> None:
        try:
            reply = await self._stub.AppendEvent(
                event,
                timeout=settings.AUDIT_APPEND_TIMEOUT_SECONDS,
            )
            if reply.status != pb.APPEND_STATUS_ACCEPTED:
                logger.warning("audit append refused status=%s", reply.status)
        except grpc.aio.AioRpcError as exc:
            logger.warning("audit append dropped code=%s", exc.code().name)
        except Exception:
            logger.warning("audit append dropped, unexpected error")
