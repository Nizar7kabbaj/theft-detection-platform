from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime

import grpc

from app.core.config import get_settings
from app.core.pseudonym import PseudonymKeyError, pseudonymize
from app.server.grpc_gen import audit_pb2 as pb
from app.server.grpc_gen import common_pb2
from app.server.grpc_gen.audit_pb2_grpc import AuditServiceStub

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = 1
_SUBJECT_DOMAIN = "auth-login-subject"

_ROLE_BY_NAME = {
    "admin": common_pb2.ROLE_ADMIN,
    "operator": common_pb2.ROLE_OPERATOR,
    "viewer": common_pb2.ROLE_VIEWER,
    "ml_engineer": common_pb2.ROLE_ML_ENGINEER,
    "compliance": common_pb2.ROLE_COMPLIANCE,
}

_GRPC_CHANNEL_OPTIONS = [
    ("grpc.keepalive_time_ms", 30_000),
    ("grpc.keepalive_timeout_ms", 10_000),
    ("grpc.max_receive_message_length", 8 * 1024 * 1024),
    ("grpc.max_send_message_length", 8 * 1024 * 1024),
]

_channel: grpc.aio.Channel | None = None
_client: AuditClient | None = None
_live_tasks: set[asyncio.Task[None]] = set()


def _roles_to_enum(roles: list[str]) -> list[int]:
    return [_ROLE_BY_NAME[name] for name in roles if name in _ROLE_BY_NAME]


class AuditClient:
    def __init__(self, stub: AuditServiceStub) -> None:
        self._stub = stub

    def _new_event(self, actor: str, severity: int) -> pb.AuditEvent:
        event = pb.AuditEvent(
            schema_version=_SCHEMA_VERSION,
            event_id=str(uuid.uuid4()),
            source_service=common_pb2.SOURCE_SERVICE_AUTH,
            actor=actor,
            severity=severity,
        )
        event.occurred_at.FromDatetime(datetime.now(UTC))
        return event

    def emit_login_success(
        self,
        subject_id: str,
        session_id: str,
        roles: list[str],
        source_ip: str,
        user_agent: str,
    ) -> None:
        event = self._new_event(subject_id, common_pb2.SEVERITY_INFO)
        payload = event.login_success
        payload.subject_id = subject_id
        payload.session_id = session_id
        payload.roles.extend(_roles_to_enum(roles))
        payload.client.source_ip = source_ip
        payload.client.user_agent = user_agent
        self._schedule(event)

    def emit_login_failure(
        self,
        username: str,
        reason: int,
        attempt_count: int,
        source_ip: str,
        user_agent: str,
    ) -> None:
        try:
            subject_hmac = pseudonymize(_SUBJECT_DOMAIN, username)
        except PseudonymKeyError:
            logger.warning("login failure not recorded, pseudonym key unavailable")
            return
        event = self._new_event("", common_pb2.SEVERITY_WARNING)
        payload = event.login_failure
        payload.subject_hmac = subject_hmac
        payload.reason = reason
        payload.attempt_count = attempt_count
        payload.client.source_ip = source_ip
        payload.client.user_agent = user_agent
        self._schedule(event)

    def emit_session_ended(
        self,
        subject_id: str,
        session_id: str,
        kind: int,
        source_ip: str,
        user_agent: str,
    ) -> None:
        event = self._new_event(subject_id, common_pb2.SEVERITY_INFO)
        payload = event.session_ended
        payload.subject_id = subject_id
        payload.session_id = session_id
        payload.kind = kind
        payload.client.source_ip = source_ip
        payload.client.user_agent = user_agent
        self._schedule(event)

    def emit_token_refreshed(
        self,
        subject_id: str,
        session_id: str,
        family_id: str,
        source_ip: str,
        user_agent: str,
    ) -> None:
        event = self._new_event(subject_id, common_pb2.SEVERITY_INFO)
        payload = event.token_refreshed
        payload.subject_id = subject_id
        payload.session_id = session_id
        payload.family_id = family_id
        payload.client.source_ip = source_ip
        payload.client.user_agent = user_agent
        self._schedule(event)

    def emit_refresh_reuse_detected(
        self,
        subject_id: str,
        session_id: str,
        family_id: str,
        source_ip: str,
        user_agent: str,
    ) -> None:
        event = self._new_event(subject_id, common_pb2.SEVERITY_CRITICAL)
        payload = event.refresh_token_reuse_detected
        payload.subject_id = subject_id
        payload.session_id = session_id
        payload.family_id = family_id
        payload.client.source_ip = source_ip
        payload.client.user_agent = user_agent
        self._schedule(event)

    def emit_throttle_triggered(
        self,
        username: str,
        observed_count: int,
        threshold: int,
        window_seconds: int,
    ) -> None:
        try:
            subject_hmac = pseudonymize(_SUBJECT_DOMAIN, username)
        except PseudonymKeyError:
            logger.warning("throttle event not recorded, pseudonym key unavailable")
            return
        event = self._new_event("", common_pb2.SEVERITY_CRITICAL)
        payload = event.auth_throttle_triggered
        payload.bucket = pb.THROTTLE_BUCKET_ACCOUNT
        payload.observed_count = observed_count
        payload.threshold = threshold
        payload.window_seconds = window_seconds
        payload.subject_hmac = subject_hmac
        self._schedule(event)

    def emit_admin_session_revoked(self, actor_user_id: str, session_id: str) -> None:
        event = self._new_event(actor_user_id, common_pb2.SEVERITY_NOTICE)
        payload = event.admin_action
        payload.actor_user_id = actor_user_id
        payload.action = pb.ADMIN_ACTION_KIND_REVOKE_SESSION
        payload.target_kind = pb.ADMIN_TARGET_KIND_SESSION
        payload.target_id = session_id
        payload.reason_code = pb.ADMIN_REASON_CODE_ROUTINE_ADMINISTRATION
        self._schedule(event)

    def _schedule(self, event: pb.AuditEvent) -> None:
        if len(_live_tasks) >= get_settings().audit_max_inflight_appends:
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
                timeout=get_settings().audit_append_timeout_seconds,
            )
            if reply.status != pb.APPEND_STATUS_ACCEPTED:
                logger.warning("audit append refused status=%s", reply.status)
        except grpc.aio.AioRpcError as exc:
            logger.warning("audit append dropped code=%s", exc.code().name)
        except Exception:
            logger.warning("audit append dropped, unexpected error")


def open_audit_client() -> AuditClient:
    global _channel, _client
    if _client is not None:
        return _client
    settings = get_settings()
    credentials = grpc.ssl_channel_credentials(
        root_certificates=settings.tls_ca_file.read_bytes(),
        private_key=settings.tls_key_file.read_bytes(),
        certificate_chain=settings.tls_cert_file.read_bytes(),
    )
    _channel = grpc.aio.secure_channel(
        settings.audit_target,
        credentials,
        options=_GRPC_CHANNEL_OPTIONS,
    )
    _client = AuditClient(AuditServiceStub(_channel))
    logger.info("audit client ready")
    return _client


def audit_client() -> AuditClient | None:
    return _client


async def drain_pending_appends() -> None:
    if not _live_tasks:
        return
    pending = tuple(_live_tasks)
    _, still_running = await asyncio.wait(
        pending, timeout=get_settings().audit_drain_timeout_seconds
    )
    if still_running:
        logger.warning("audit appends abandoned at shutdown count=%d", len(still_running))


async def close_audit_client() -> None:
    global _channel, _client
    if _channel is not None:
        await _channel.close(grace=2)
        _channel = None
    _client = None
    logger.info("audit client closed")
