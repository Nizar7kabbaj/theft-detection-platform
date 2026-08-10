from __future__ import annotations

import logging

import grpc
from google.protobuf.timestamp_pb2 import Timestamp
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import get_sessionmaker
from app.core.config import get_settings
from app.core.redis import is_token_revoked, revoke_sid
from app.core.tokens import TokenError, TokenFailure, decode_access_token
from app.repositories.session_repository import SessionRepository
from app.server.grpc_gen import audit_pb2 as pb
from app.server.grpc_gen import auth_pb2, auth_pb2_grpc
from app.services.audit_service import audit_client

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
            await context.abort(
                grpc.StatusCode.UNAVAILABLE, "revocation store unavailable"
            )
        if revoked:
            return auth_pb2.VerifyTokenReply(
                status=auth_pb2.VERIFICATION_STATUS_REVOKED
            )
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
        except SQLAlchemyError:
            logger.warning(
                "session store unavailable, session_id=%s", request.session_id
            )
            await context.abort(
                grpc.StatusCode.UNAVAILABLE, "session store unavailable"
            )
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
                await db.commit()
        except SQLAlchemyError:
            logger.warning(
                "session store unavailable, session_id=%s", request.session_id
            )
            await context.abort(
                grpc.StatusCode.UNAVAILABLE, "session store unavailable"
            )
        if was_live:
            try:
                await revoke_sid(
                    request.session_id, get_settings().access_token_ttl_seconds
                )
            except RedisError:
                logger.error(
                    "session revoked in store but not in cache, session_id=%s",
                    request.session_id,
                )
        client = audit_client()
        if client is not None and was_live:
            client.emit_session_ended(
                subject_id=subject_id,
                session_id=request.session_id,
                kind=pb.SESSION_END_KIND_REVOKED,
                source_ip="",
                user_agent="",
            )
            if request.revoked_by:
                client.emit_admin_session_revoked(
                    actor_user_id=request.revoked_by,
                    session_id=request.session_id,
                )
        return auth_pb2.RevokeSessionReply(
            revoked=existed,
            revoked_at=_now_timestamp(),
        )
