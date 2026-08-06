from __future__ import annotations

import contextvars
import logging

import grpc

from app.server.identity import IdentityError, source_service_from_pem

logger = logging.getLogger(__name__)

_PEER_SERVICE: contextvars.ContextVar[int] = contextvars.ContextVar("peer_service")


def peer_service() -> int:
    return _PEER_SERVICE.get(0)


def _peer_certificate(context: grpc.aio.ServicerContext) -> bytes:
    chain = context.auth_context().get("x509_pem_cert")
    if not chain:
        return b""
    return chain[0]


class IdentityInterceptor(grpc.aio.ServerInterceptor):
    async def intercept_service(self, continuation, handler_call_details):
        handler = await continuation(handler_call_details)
        if handler is None:
            return None
        if handler.request_streaming or handler.response_streaming:
            return handler

        inner = handler.unary_unary

        async def wrapper(request, context):
            try:
                derived = source_service_from_pem(_peer_certificate(context))
            except IdentityError:
                logger.warning("peer identity rejected")
                await context.abort(
                    grpc.StatusCode.UNAUTHENTICATED, "caller identity not established"
                )
            token = _PEER_SERVICE.set(derived)
            try:
                return await inner(request, context)
            finally:
                _PEER_SERVICE.reset(token)

        return grpc.unary_unary_rpc_method_handler(
            wrapper,
            request_deserializer=handler.request_deserializer,
            response_serializer=handler.response_serializer,
        )
