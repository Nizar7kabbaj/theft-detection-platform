from __future__ import annotations

import asyncio
import contextlib
import socket
from collections.abc import AsyncIterator
from urllib.parse import urlparse, urlunparse

import grpc
import httpx
import pytest
import pytest_asyncio
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from motor.motor_asyncio import (
    AsyncIOMotorClient,
    AsyncIOMotorCollection,
    AsyncIOMotorDatabase,
)
from redis.asyncio import Redis

from app.api.v1 import alerts, cameras, detections, stats, streams
from app.core.config import settings
from app.core.errors import (
    AlertUnavailable,
    AppError,
    ConflictError,
    InferenceUnavailable,
    NotFoundError,
    ValidationError,
)
from app.core.redis import get_redis
from app.dependencies import get_db
from app.grpc_gen.alert_pb2_grpc import AlertServiceStub
from app.grpc_gen.inference_pb2_grpc import InferenceServiceStub
from app.services.broadcast_service import BroadcastService


INTEGRATION_REDIS_DB = 15
TEST_COLLECTION_PREFIX = "test_"


def _mongo_url() -> str:
    return settings.MONGODB_URL_LOCAL


def _redis_url_for_test_db() -> str:
    parsed = urlparse(settings.REDIS_URL_LOCAL)
    return urlunparse(parsed._replace(path=f"/{INTEGRATION_REDIS_DB}"))


def _free_port() -> int:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _PrefixedDatabase:

    def __init__(self, real: AsyncIOMotorDatabase, prefix: str) -> None:
        self._real = real
        self._prefix = prefix

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
    client = Redis.from_url(_redis_url_for_test_db(), decode_responses=True)
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
async def alert_channel(
    channel_credentials: grpc.ChannelCredentials,
) -> AsyncIterator[grpc.aio.Channel]:
    channel = grpc.aio.secure_channel(settings.NOTIFICATION_TARGET, channel_credentials)
    yield channel
    await channel.close()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def alert_stub(alert_channel: grpc.aio.Channel) -> AlertServiceStub:
    return AlertServiceStub(alert_channel)


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

    @app.exception_handler(InferenceUnavailable)
    async def _iu(_: Request, exc: InferenceUnavailable) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(AlertUnavailable)
    async def _au(_: Request, exc: AlertUnavailable) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(AppError)
    async def _app(_: Request, _exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": "internal error"})


async def _ensure_indexes(real_db: AsyncIOMotorDatabase, prefix: str) -> None:
    cameras_col = real_db[f"{prefix}cameras"]
    detections_col = real_db[f"{prefix}detections"]
    alerts_col = real_db[f"{prefix}alerts"]
    for col in (cameras_col, detections_col, alerts_col):
        try:
            await col.drop_indexes()
        except Exception:
            pass
    await cameras_col.create_index("name", unique=True)
    await detections_col.create_index([("session_id", 1), ("occurred_at", -1)])
    await alerts_col.create_index([("acknowledged", 1), ("created_at", -1)])


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def test_app(
    real_db: AsyncIOMotorDatabase,
    test_db: _PrefixedDatabase,
    redis_client: Redis,
    inference_stub: InferenceServiceStub,
    alert_stub: AlertServiceStub,
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
    app.dependency_overrides[get_db] = lambda: test_db
    app.dependency_overrides[get_redis] = lambda: redis_client
    return app


@pytest_asyncio.fixture(loop_scope="session")
async def client(test_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=test_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as c:
        yield c


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def ws_server(
    redis_client: Redis,
) -> AsyncIterator[tuple[str, BroadcastService]]:
    app = FastAPI()
    app.include_router(streams.router)
    broadcaster = BroadcastService(
        redis=redis_client,
        max_connections=64,
        heartbeat_seconds=30,
    )
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


@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def _clean_redis(redis_client: Redis) -> AsyncIterator[None]:
    yield
    await redis_client.flushdb()
