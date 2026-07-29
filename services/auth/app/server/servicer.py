from __future__ import annotations

import logging

import grpc
from google.protobuf.timestamp_pb2 import Timestamp

from app.server.grpc_gen import auth_pb2, auth_pb2_grpc

logger = logging.getLogger(__name__)

_STUB_USER_ID = "stub-user-id"
_STUB_USERNAME = "stub-user"
_STUB_ROLES = ("viewer",)
_STUB_SESSION_ID = "stub-session-id"
_STUB_EXPIRES_IN_SECONDS = 900


def _future_timestamp(seconds_ahead: int) -> Timestamp:
    ts = Timestamp()
    ts.GetCurrentTime()
    ts.seconds += seconds_ahead
    return ts


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
        logger.info("verify token request, audience=%s", request.expected_audience)
        return auth_pb2.VerifyTokenReply(
            status=auth_pb2.VERIFICATION_STATUS_VALID,
            user_id=_STUB_USER_ID,
            username=_STUB_USERNAME,
            roles=list(_STUB_ROLES),
            expires_at=_future_timestamp(_STUB_EXPIRES_IN_SECONDS),
            session_id=_STUB_SESSION_ID,
        )

    async def IntrospectSession(
        self,
        request: auth_pb2.IntrospectSessionRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.IntrospectSessionReply:
        logger.info("introspect session request, session_id=%s", request.session_id)
        return auth_pb2.IntrospectSessionReply(
            active=True,
            user_id=_STUB_USER_ID,
            issued_at=_now_timestamp(),
            last_used_at=_now_timestamp(),
            source_ip="",
            user_agent="",
        )

    async def RevokeSession(
        self,
        request: auth_pb2.RevokeSessionRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.RevokeSessionReply:
        logger.info("revoke session request, session_id=%s", request.session_id)
        return auth_pb2.RevokeSessionReply(
            revoked=True,
            revoked_at=_now_timestamp(),
        )
