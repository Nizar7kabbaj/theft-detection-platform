from __future__ import annotations

import logging

import grpc
from motor.motor_asyncio import AsyncIOMotorDatabase
from opentelemetry.instrumentation.grpc import aio_server_interceptor
from redis.asyncio import Redis

from app.core.config import settings
from app.grpc_gen import decision_pb2_grpc
from app.grpc_gen.alert_pb2_grpc import AlertServiceStub
from app.grpc_gen.auth_pb2_grpc import AuthServiceStub
from app.grpc_server.decision_servicer import AlertDecisionServicer
from app.grpc_server.interceptors import IdentityInterceptor
from app.services.alert_service import AlertClient
from app.services.auth_service import AuthClient

logger = logging.getLogger(__name__)

_SERVER_OPTIONS = [
    ("grpc.max_receive_message_length", 64 * 1024),
    ("grpc.max_send_message_length", 64 * 1024),
    ("grpc.keepalive_permit_without_calls", 1),
]


async def start_decision_server(
    database: AsyncIOMotorDatabase,
    redis: Redis,
    alert_stub: AlertServiceStub,
    auth_stub: AuthServiceStub,
) -> grpc.aio.Server:
    server = grpc.aio.server(
        interceptors=[aio_server_interceptor(), IdentityInterceptor()],
        options=_SERVER_OPTIONS,
    )
    decision_pb2_grpc.add_AlertDecisionServiceServicer_to_server(
        AlertDecisionServicer(database, redis, AlertClient(alert_stub), AuthClient(auth_stub)),
        server,
    )
    credentials = grpc.ssl_server_credentials(
        [(settings.TLS_KEY_FILE.read_bytes(), settings.TLS_CERT_FILE.read_bytes())],
        root_certificates=settings.TLS_CA_FILE.read_bytes(),
        require_client_auth=True,
    )
    address = f"{settings.DECISION_GRPC_HOST}:{settings.DECISION_GRPC_PORT}"
    server.add_secure_port(address, credentials)
    await server.start()
    logger.info("decision grpc listening port=%d", settings.DECISION_GRPC_PORT)
    return server
