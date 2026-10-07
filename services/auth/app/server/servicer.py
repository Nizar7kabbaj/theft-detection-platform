from __future__ import annotations

import logging
import uuid

import grpc
from google.protobuf.timestamp_pb2 import Timestamp
from redis.exceptions import RedisError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.config import get_settings
from app.core.database import get_sessionmaker
from app.core.redis import consume_telegram_link, is_token_revoked, revoke_sid
from app.core.telegram_link import hash_link_token, is_well_formed_link_token
from app.core.tokens import TokenError, TokenFailure, decode_access_token
from app.repositories.audit_outbox_repository import AuditOutboxRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.telegram_binding_repository import TelegramBindingRepository
from app.repositories.user_repository import UserRepository
from app.server.grpc_gen import audit_pb2 as pb
from app.server.grpc_gen import auth_pb2, auth_pb2_grpc, common_pb2
from app.server.interceptors import peer_service
from app.services import audit_service as audit_events

logger = logging.getLogger(__name__)

_FAILURE_STATUS = {
    TokenFailure.EXPIRED: auth_pb2.VERIFICATION_STATUS_EXPIRED,
    TokenFailure.AUDIENCE_MISMATCH: auth_pb2.VERIFICATION_STATUS_AUDIENCE_MISMATCH,
    TokenFailure.SIGNATURE_INVALID: auth_pb2.VERIFICATION_STATUS_SIGNATURE_INVALID,
    TokenFailure.MALFORMED: auth_pb2.VERIFICATION_STATUS_MALFORMED,
}


def _now_timestamp() -> Timestamp:
    ts = Timestamp()
    ts.GetCurrentTime()
    return ts


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return True


async def _require_caller(context: grpc.aio.ServicerContext, allowed: int, rpc: str) -> None:
    caller = peer_service()
    if caller != allowed:
        logger.warning("%s refused for caller %d", rpc, caller)
        await context.abort(grpc.StatusCode.PERMISSION_DENIED, "caller is not allowed")


class AuthServicer(auth_pb2_grpc.AuthServiceServicer):
    async def VerifyToken(
        self,
        request: auth_pb2.VerifyTokenRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.VerifyTokenReply:
        try:
            claims = decode_access_token(request.token)
        except TokenError as exc:
            return auth_pb2.VerifyTokenReply(status=_FAILURE_STATUS[exc.failure])
        jti = claims["jti"]
        session_id = claims["sid"]
        try:
            revoked = await is_token_revoked(jti, session_id)
        except RedisError:
            logger.warning("revocation check unavailable, jti=%s", jti)
            await context.abort(grpc.StatusCode.UNAVAILABLE, "revocation store unavailable")
        if revoked:
            return auth_pb2.VerifyTokenReply(status=auth_pb2.VERIFICATION_STATUS_REVOKED)
        expires_at = Timestamp()
        expires_at.FromSeconds(int(claims["exp"]))
        return auth_pb2.VerifyTokenReply(
            status=auth_pb2.VERIFICATION_STATUS_VALID,
            user_id=claims["sub"],
            username=claims["username"],
            roles=list(claims.get("roles", [])),
            expires_at=expires_at,
            session_id=claims["sid"],
        )

    async def IntrospectSession(
        self,
        request: auth_pb2.IntrospectSessionRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.IntrospectSessionReply:
        factory = get_sessionmaker()
        try:
            async with factory() as db:
                sessions = SessionRepository(db)
                login_session = await sessions.get_by_id(request.session_id)
                roles: list[str] = []
                if login_session is not None:
                    users = UserRepository(db)
                    user = await users.get_by_id(login_session.user_id)
                    if user is not None and user.is_active:
                        roles = list(user.roles)
        except SQLAlchemyError:
            logger.warning("session store unavailable, session_id=%s", request.session_id)
            await context.abort(grpc.StatusCode.UNAVAILABLE, "session store unavailable")
        if login_session is None:
            return auth_pb2.IntrospectSessionReply(active=False)
        issued_at = Timestamp()
        issued_at.FromDatetime(login_session.created_at)
        last_used_at = Timestamp()
        last_used_at.FromDatetime(login_session.last_used_at)
        return auth_pb2.IntrospectSessionReply(
            active=not login_session.revoked,
            user_id=login_session.user_id,
            issued_at=issued_at,
            last_used_at=last_used_at,
            source_ip=login_session.source_ip,
            user_agent=login_session.user_agent,
            roles=roles,
        )

    async def LookupOperator(
        self,
        request: auth_pb2.LookupOperatorRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.LookupOperatorReply:
        await _require_caller(context, common_pb2.SOURCE_SERVICE_API, "lookup operator")
        subject = request.WhichOneof("subject")
        if subject is None:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "subject required")
        if subject == "user_id" and not _is_uuid(request.user_id):
            return auth_pb2.LookupOperatorReply(found=False)
        factory = get_sessionmaker()
        try:
            async with factory() as db:
                users = UserRepository(db)
                if subject == "telegram_user_id":
                    binding = await TelegramBindingRepository(db).get_by_telegram_id(
                        request.telegram_user_id
                    )
                    user = None if binding is None else await users.get_by_id(binding.user_id)
                else:
                    user = await users.get_by_id(request.user_id)
        except SQLAlchemyError:
            logger.warning("user store unavailable during operator lookup")
            await context.abort(grpc.StatusCode.UNAVAILABLE, "user store unavailable")
        if user is None:
            return auth_pb2.LookupOperatorReply(found=False)
        return auth_pb2.LookupOperatorReply(
            found=True,
            user_id=user.id,
            username=user.username,
            roles=list(user.roles),
            active=user.is_active,
        )

    async def BindTelegram(
        self,
        request: auth_pb2.BindTelegramRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.BindTelegramReply:
        await _require_caller(context, common_pb2.SOURCE_SERVICE_NOTIFICATION, "bind telegram")
        invalid = auth_pb2.BindTelegramReply(status=auth_pb2.BIND_TELEGRAM_STATUS_TOKEN_INVALID)
        if request.telegram_user_id <= 0 or not is_well_formed_link_token(request.link_token):
            return invalid
        try:
            user_id = await consume_telegram_link(hash_link_token(request.link_token))
        except RedisError:
            logger.warning("link store unavailable during telegram bind")
            await context.abort(grpc.StatusCode.UNAVAILABLE, "link store unavailable")
        if user_id is None:
            return invalid
        factory = get_sessionmaker()
        try:
            async with factory() as db:
                user = await UserRepository(db).get_by_id(user_id)
                if user is None or not user.is_active:
                    return invalid
                username = user.username
                bindings = TelegramBindingRepository(db)
                current = await bindings.get_for_user(user.id)
                previous = None if current is None else current.telegram_user_id
                if previous == request.telegram_user_id:
                    return auth_pb2.BindTelegramReply(
                        status=auth_pb2.BIND_TELEGRAM_STATUS_BOUND, username=username
                    )
                await bindings.bind(user.id, request.telegram_user_id)
                event = audit_events.telegram_link_changed(
                    actor_user_id=user.id, before=previous, after=request.telegram_user_id
                )
                await AuditOutboxRepository(db).enqueue(
                    event.event_id, event.event_bytes, event.occurred_at
                )
                await db.commit()
        except IntegrityError:
            logger.info("telegram account already linked to another user")
            return auth_pb2.BindTelegramReply(status=auth_pb2.BIND_TELEGRAM_STATUS_ACCOUNT_IN_USE)
        except SQLAlchemyError:
            logger.warning("user store unavailable during telegram bind")
            await context.abort(grpc.StatusCode.UNAVAILABLE, "user store unavailable")
        logger.info("telegram account linked user_id=%s", user_id)
        return auth_pb2.BindTelegramReply(
            status=auth_pb2.BIND_TELEGRAM_STATUS_BOUND, username=username
        )

    async def RevokeSession(
        self,
        request: auth_pb2.RevokeSessionRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.RevokeSessionReply:
        factory = get_sessionmaker()
        try:
            async with factory() as db:
                sessions = SessionRepository(db)
                revoked_session = await sessions.get_by_id(request.session_id)
                subject_id = "" if revoked_session is None else revoked_session.user_id
                existed = revoked_session is not None
                was_live = await sessions.revoke(request.session_id)
                if was_live:
                    outbox = AuditOutboxRepository(db)
                    ended = audit_events.session_ended(
                        subject_id=subject_id,
                        session_id=request.session_id,
                        kind=pb.SESSION_END_KIND_REVOKED,
                        source_ip="",
                        user_agent="",
                    )
                    await outbox.enqueue(ended.event_id, ended.event_bytes, ended.occurred_at)
                    if request.revoked_by:
                        admin = audit_events.admin_session_revoked(
                            actor_user_id=request.revoked_by,
                            session_id=request.session_id,
                        )
                        await outbox.enqueue(admin.event_id, admin.event_bytes, admin.occurred_at)
                await db.commit()
        except SQLAlchemyError:
            logger.warning("session store unavailable, session_id=%s", request.session_id)
            await context.abort(grpc.StatusCode.UNAVAILABLE, "session store unavailable")
        if was_live:
            try:
                await revoke_sid(request.session_id, get_settings().access_token_ttl_seconds)
            except RedisError:
                logger.error(
                    "session revoked in store but not in cache, session_id=%s",
                    request.session_id,
                )
        return auth_pb2.RevokeSessionReply(
            revoked=existed,
            revoked_at=_now_timestamp(),
        )
