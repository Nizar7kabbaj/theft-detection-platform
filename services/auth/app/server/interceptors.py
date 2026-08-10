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


def _resolve_peer(context: grpc.aio.ServicerContext) -> int:
    return source_service_from_pem(_peer_certificate(context))


class IdentityInterceptor(grpc.aio.ServerInterceptor):
    async def intercept_service(self, continuation, handler_call_details):
        handler = await continuation(handler_call_details)
        if handler is None:
            return None
        if handler.unary_unary is not None:
            return grpc.unary_unary_rpc_method_handler(
                self._wrap_unary_unary(handler.unary_unary),
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )
        if handler.unary_stream is not None:
            return grpc.unary_stream_rpc_method_handler(
                self._wrap_stream_response(handler.unary_stream),
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )
        if handler.stream_unary is not None:
            return grpc.stream_unary_rpc_method_handler(
                self._wrap_unary_response(handler.stream_unary),
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )
        if handler.stream_stream is not None:
            return grpc.stream_stream_rpc_method_handler(
                self._wrap_stream_response(handler.stream_stream),
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )
        return handler

    def _wrap_unary_unary(self, inner):
        async def wrapper(request, context):
            try:
                derived = _resolve_peer(context)
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

        return wrapper

    def _wrap_unary_response(self, inner):
        async def wrapper(request_iterator, context):
            try:
                derived = _resolve_peer(context)
            except IdentityError:
                logger.warning("peer identity rejected")
                await context.abort(
                    grpc.StatusCode.UNAUTHENTICATED, "caller identity not established"
                )
            token = _PEER_SERVICE.set(derived)
            try:
                return await inner(request_iterator, context)
            finally:
                _PEER_SERVICE.reset(token)

        return wrapper

    def _wrap_stream_response(self, inner):
        async def wrapper(request, context):
            try:
                derived = _resolve_peer(context)
            except IdentityError:
                logger.warning("peer identity rejected")
                await context.abort(
                    grpc.StatusCode.UNAUTHENTICATED, "caller identity not established"
                )
            token = _PEER_SERVICE.set(derived)
            try:
                async for response in inner(request, context):
                    yield response
            finally:
                _PEER_SERVICE.reset(token)

        return wrapper
