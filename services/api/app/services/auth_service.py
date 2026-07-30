from __future__ import annotations

import logging
from dataclasses import dataclass

import grpc
from opentelemetry import trace

from app.core.config import settings
from app.core.errors import AuthUnavailable
from app.grpc_gen import auth_pb2 as pb
from app.grpc_gen.auth_pb2_grpc import AuthServiceStub

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

_TRANSIENT_CODES = {
    grpc.StatusCode.UNAVAILABLE,
    grpc.StatusCode.DEADLINE_EXCEEDED,
}


@dataclass(frozen=True, slots=True)
class VerifyResult:
    status: int
    user_id: str
    username: str
    roles: frozenset[str]
    session_id: str

    @property
    def is_valid(self) -> bool:
        return self.status == pb.VerificationStatus.VERIFICATION_STATUS_VALID


class AuthClient:
    def __init__(self, stub: AuthServiceStub) -> None:
        self._stub = stub

    async def verify_token(
        self,
        token: str,
        source_ip: str,
        user_agent: str,
    ) -> VerifyResult:
        request = pb.VerifyTokenRequest(
            token=token,
            source_ip=source_ip,
            user_agent=user_agent,
        )
        with tracer.start_as_current_span("auth.verify_token") as span:
            try:
                response = await self._stub.VerifyToken(
                    request,
                    timeout=settings.AUTH_VERIFY_TIMEOUT_SECONDS,
                )
            except grpc.aio.AioRpcError as exc:
                if exc.code() in _TRANSIENT_CODES:
                    logger.warning(
                        "auth call failed code=%s detail=%s",
                        exc.code().name,
                        exc.details(),
                    )
                    raise AuthUnavailable("auth service unavailable") from exc
                raise
            span.set_attribute(
                "auth.status",
                pb.VerificationStatus.Name(response.status),
            )
            return VerifyResult(
                status=response.status,
                user_id=response.user_id,
                username=response.username,
                roles=frozenset(response.roles),
                session_id=response.session_id,
            )
