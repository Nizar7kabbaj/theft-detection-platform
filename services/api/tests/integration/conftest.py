from __future__ import annotations

import asyncio
import contextlib
import socket
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlparse, urlunparse

import grpc
import httpx
import pytest
import pytest_asyncio
import trustme
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from motor.motor_asyncio import (
    AsyncIOMotorClient,
    AsyncIOMotorCollection,
    AsyncIOMotorDatabase,
)
from redis.asyncio import Redis
from typing_extensions import override

from app.api.v1 import alerts, cameras, detections, stats, streams
from app.core.authz import get_current_user
from app.core.config import settings
from app.core.errors import (
    AlertUnavailableError,
    AppError,
    ConflictError,
    InferenceUnavailableError,
    NotFoundError,
    ValidationError,
)
from app.core.redis import get_redis
from app.dependencies import get_db
from app.grpc_gen import alert_pb2, alert_pb2_grpc
from app.grpc_gen.inference_pb2_grpc import InferenceServiceStub
from app.migrations.runner import discover_versions
from app.schemas.identity import CurrentUser
from app.services.broadcast_service import BroadcastService
from app.services.revocation_service import RevocationService

INTEGRATION_REDIS_DB = 15
TEST_COLLECTION_PREFIX = "test_"
TEST_USER = CurrentUser(
    user_id="65f1a2b3c4d5e6f7a8b9c0d2",
    username="integration-admin",
    roles=frozenset({"admin"}),
    session_id="integration-session",
)
ALERT_TEST_HOST = "alert.integration.test"
ALERT_TEST_CLIENT = "api.integration.test"


class RecordingAlertServicer(alert_pb2_grpc.AlertServiceServicer):
    def __init__(self) -> None:
        self.sent: list[alert_pb2.Alert] = []

    @override
    async def SendAlert(
        self, request: alert_pb2.Alert, context: grpc.aio.ServicerContext
    ) -> alert_pb2.SendAlertReply:
        self.sent.append(request)
        return alert_pb2.SendAlertReply(status=alert_pb2.STATUS_ACCEPTED)

    @override
    async def GetDeliveryStatus(
        self, request: alert_pb2.DeliveryStatusRequest, context: grpc.aio.ServicerContext
    ) -> alert_pb2.DeliveryStatusReply:
        return alert_pb2.DeliveryStatusReply(known=False)

    @override
    async def GetDeliveryStatusBatch(
        self, request: alert_pb2.DeliveryStatusBatchRequest, context: grpc.aio.ServicerContext
    ) -> alert_pb2.DeliveryStatusBatchReply:
        return alert_pb2.DeliveryStatusBatchReply()


def _mongo_url() -> str:
    from app.core.database import _resolve_mongodb_url

    return _resolve_mongodb_url()


def _redis_url_for_test_db() -> str:
    from app.core.redis import _resolve_redis_url

    parsed = urlparse(_resolve_redis_url())
    return urlunparse(parsed._replace(path=f"/{INTEGRATION_REDIS_DB}"))


def _free_port() -> int:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _PrefixedDatabase:
    def __init__(self, real: AsyncIOMotorDatabase, prefix: str) -> None:
        self._real = real
        self._prefix = prefix

    def get_collection(self, name: str, **kwargs: Any) -> AsyncIOMotorCollection:
        return self._real.get_collection(f"{self._prefix}{name}", **kwargs)

    def __getattr__(self, name: str) -> AsyncIOMotorCollection:
        return self._real[f"{self._prefix}{name}"]

    def __getitem__(self, name: str) -> AsyncIOMotorCollection:
        return self._real[f"{self._prefix}{name}"]


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def mongo_client() -> AsyncIterator[AsyncIOMotorClient]:
    client = AsyncIOMotorClient(_mongo_url())
    yield client
    client.close()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def real_db(mongo_client: AsyncIOMotorClient) -> AsyncIOMotorDatabase:
    return mongo_client[settings.DATABASE_NAME]


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def test_db(real_db: AsyncIOMotorDatabase) -> _PrefixedDatabase:
    return _PrefixedDatabase(real_db, TEST_COLLECTION_PREFIX)


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def redis_client() -> AsyncIterator[Redis]:
    from app.core.redis import _tls_options

    client = Redis.from_url(
        _redis_url_for_test_db(),
        decode_responses=True,
        **_tls_options(),
    )
    yield client
    await client.aclose()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def stream_redis_client() -> AsyncIterator[Redis]:
    from app.core.redis import open_stream_redis

    client = await open_stream_redis()
    yield client
    await client.aclose()


@pytest.fixture(scope="session")
def channel_credentials() -> grpc.ChannelCredentials:
    return grpc.ssl_channel_credentials(
        root_certificates=settings.TLS_CA_FILE.read_bytes(),
        private_key=settings.TLS_KEY_FILE.read_bytes(),
        certificate_chain=settings.TLS_CERT_FILE.read_bytes(),
    )


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def inference_channel(
    channel_credentials: grpc.ChannelCredentials,
) -> AsyncIterator[grpc.aio.Channel]:
    channel = grpc.aio.secure_channel(settings.INFERENCE_TARGET, channel_credentials)
    yield channel
    await channel.close()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def inference_stub(
    inference_channel: grpc.aio.Channel,
) -> InferenceServiceStub:
    return InferenceServiceStub(inference_channel)


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def alert_service() -> AsyncIterator[tuple[RecordingAlertServicer, grpc.aio.Channel]]:
    ca = trustme.CA()
    server_cert = ca.issue_cert(ALERT_TEST_HOST)
    client_cert = ca.issue_cert(ALERT_TEST_CLIENT)
    servicer = RecordingAlertServicer()
    server = grpc.aio.server()
    alert_pb2_grpc.add_AlertServiceServicer_to_server(servicer, server)
    server_credentials = grpc.ssl_server_credentials(
        [(server_cert.private_key_pem.bytes(), server_cert.cert_chain_pems[0].bytes())],
        root_certificates=ca.cert_pem.bytes(),
        require_client_auth=True,
    )
    port = server.add_secure_port("127.0.0.1:0", server_credentials)
    await server.start()
    channel = grpc.aio.secure_channel(
        f"127.0.0.1:{port}",
        grpc.ssl_channel_credentials(
            root_certificates=ca.cert_pem.bytes(),
            private_key=client_cert.private_key_pem.bytes(),
            certificate_chain=client_cert.cert_chain_pems[0].bytes(),
        ),
        options=[("grpc.ssl_target_name_override", ALERT_TEST_HOST)],
    )
    try:
        yield servicer, channel
    finally:
        await channel.close()
        await server.stop(grace=None)


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def alert_stub(
    alert_service: tuple[RecordingAlertServicer, grpc.aio.Channel],
) -> alert_pb2_grpc.AlertServiceStub:
    return alert_pb2_grpc.AlertServiceStub(alert_service[1])


@pytest.fixture
def sent_alerts(
    alert_service: tuple[RecordingAlertServicer, grpc.aio.Channel],
) -> list[alert_pb2.Alert]:
    alert_service[0].sent.clear()
    return alert_service[0].sent


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(NotFoundError)
    async def _nf(_: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ConflictError)
    async def _cf(_: Request, exc: ConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(ValidationError)
    async def _val(_: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(InferenceUnavailableError)
    async def _iu(_: Request, exc: InferenceUnavailableError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(AlertUnavailableError)
    async def _au(_: Request, exc: AlertUnavailableError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(AppError)
    async def _app(_: Request, _exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": "internal error"})


async def _ensure_indexes(real_db: AsyncIOMotorDatabase, prefix: str) -> None:
    for name in await real_db.list_collection_names():
        if name.startswith(prefix):
            await real_db[name].drop()
    schema = _PrefixedDatabase(real_db, prefix)
    for _, _, module in discover_versions():
        await module.up(schema)


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def test_app(
    real_db: AsyncIOMotorDatabase,
    test_db: _PrefixedDatabase,
    redis_client: Redis,
    stream_redis_client: Redis,
    inference_stub: InferenceServiceStub,
    alert_stub: alert_pb2_grpc.AlertServiceStub,
) -> FastAPI:
    await _ensure_indexes(real_db, TEST_COLLECTION_PREFIX)
    app = FastAPI()
    _register_error_handlers(app)
    app.include_router(cameras.router, prefix="/api/v1")
    app.include_router(detections.router, prefix="/api/v1")
    app.include_router(alerts.router, prefix="/api/v1")
    app.include_router(stats.router, prefix="/api/v1")
    app.state.inference_stub = inference_stub
    app.state.alert_stub = alert_stub
    app.state.redis = redis_client
    app.state.stream_redis = stream_redis_client

    async def _current_user() -> CurrentUser:
        return TEST_USER

    app.dependency_overrides[get_db] = lambda: test_db
    app.dependency_overrides[get_redis] = lambda: redis_client
    app.dependency_overrides[get_current_user] = _current_user
    return app


@pytest_asyncio.fixture(loop_scope="session")
async def client(test_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=test_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def ws_server(
    redis_client: Redis,
) -> AsyncIterator[tuple[str, BroadcastService]]:
    app = FastAPI()
    from app.core import ws_authz

    async def _authenticate(ws) -> CurrentUser:
        return TEST_USER

    ws_authz.authenticate = _authenticate

    async def _reverify_loop(ws, user, permission) -> None:
        await asyncio.Event().wait()

    streams.reverify_loop = _reverify_loop
    app.include_router(streams.router)
    broadcaster = BroadcastService(
        redis=redis_client,
        max_connections=64,
        heartbeat_seconds=30,
    )
    app.state.revocations = RevocationService(redis_client)
    app.state.broadcaster = broadcaster
    await broadcaster.start()

    port = _free_port()
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="error",
        lifespan="off",
    )
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve(), name="ws-test-uvicorn")

    for _ in range(50):
        if server.started:
            break
        await asyncio.sleep(0.05)
    if not server.started:
        raise RuntimeError("test ws server failed to start")

    base_url = f"ws://127.0.0.1:{port}"
    try:
        yield base_url, broadcaster
    finally:
        server.should_exit = True
        await broadcaster.stop()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task


@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def _clean_mongo(real_db: AsyncIOMotorDatabase) -> AsyncIterator[None]:
    yield
    names = await real_db.list_collection_names()
    for name in names:
        if name.startswith(TEST_COLLECTION_PREFIX):
            await real_db[name].delete_many({})


_CLEAN_PREFIXES = ("cache:*", "idem:*")


@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def _clean_redis(redis_client: Redis) -> AsyncIterator[None]:
    yield
    for pattern in _CLEAN_PREFIXES:
        keys = [key async for key in redis_client.scan_iter(pattern)]
        if keys:
            await redis_client.delete(*keys)
