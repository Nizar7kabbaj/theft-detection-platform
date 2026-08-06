import logging
from contextlib import asynccontextmanager
import grpc


from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from opentelemetry.instrumentation.grpc import aio_client_interceptors


from .api.v1 import alerts, cameras, detections, stats, streams
from .core.config import settings
from .core.csrf import csrf_protect
from .core.database import (
    close_mongodb_connection,
    connect_to_mongodb,
    get_database,
)
from .core.errors import (
    AlertUnavailable,
    AppError,
    AuthUnavailable,
    ConflictError,
    InferenceUnavailable,
    NotFoundError,
    ValidationError,
)
from .core.rate_limit import RateLimited, rate_limit
from .core.redis import close_redis, open_redis
from .grpc_gen.alert_pb2_grpc import AlertServiceStub
from .grpc_gen.audit_pb2_grpc import AuditServiceStub
from .grpc_gen.auth_pb2_grpc import AuthServiceStub
from .grpc_gen.inference_pb2_grpc import InferenceServiceStub
from .observability import setup_observability
from .services.broadcast_service import BroadcastService
from .services.audit_service import drain_pending_appends

logger = logging.getLogger(__name__)
_GRPC_CHANNEL_OPTIONS = [
    ("grpc.keepalive_time_ms", 30_000),
    ("grpc.keepalive_timeout_ms", 10_000),
    ("grpc.max_receive_message_length", 8 * 1024 * 1024),
    ("grpc.max_send_message_length", 8 * 1024 * 1024),
]
async def _create_indexes() -> None:
    db = get_database()
    await db.cameras.create_index("name", unique=True)
    await db.detections.create_index([("session_id", 1), ("occurred_at", -1)])
    await db.alerts.create_index([("acknowledged", 1), ("created_at", -1)])
    logger.info("startup indexes ready")
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("backend starting")
    await connect_to_mongodb()
    await _create_indexes()
    app.state.redis = await open_redis()
    app.state.broadcaster = BroadcastService(
        redis=app.state.redis,
        max_connections=settings.WS_MAX_CONNECTIONS,
        heartbeat_seconds=settings.WS_HEARTBEAT_SECONDS,
    )
    await app.state.broadcaster.start()
    app.state.inference_channel = grpc.aio.insecure_channel(
        settings.INFERENCE_TARGET,
        options=_GRPC_CHANNEL_OPTIONS,
        interceptors=aio_client_interceptors(),
    )
    app.state.inference_stub = InferenceServiceStub(app.state.inference_channel)
    app.state.alert_channel = grpc.aio.insecure_channel(
        settings.NOTIFICATION_TARGET,
        options=_GRPC_CHANNEL_OPTIONS,
        interceptors=aio_client_interceptors(),
    )
    app.state.alert_stub = AlertServiceStub(app.state.alert_channel)
    app.state.auth_channel = grpc.aio.insecure_channel(
        settings.AUTH_TARGET,
        options=_GRPC_CHANNEL_OPTIONS,
        interceptors=aio_client_interceptors(),
    )
    app.state.auth_stub = AuthServiceStub(app.state.auth_channel)
    audit_credentials = grpc.ssl_channel_credentials(
        root_certificates=settings.AUDIT_TLS_CA_FILE.read_bytes(),
        private_key=settings.AUDIT_TLS_KEY_FILE.read_bytes(),
        certificate_chain=settings.AUDIT_TLS_CERT_FILE.read_bytes(),
    )
    app.state.audit_channel = grpc.aio.secure_channel(
        settings.AUDIT_TARGET,
        audit_credentials,
        options=_GRPC_CHANNEL_OPTIONS,
        interceptors=aio_client_interceptors(),
    )
    app.state.audit_stub = AuditServiceStub(app.state.audit_channel)
    logger.info("backend ready")
    yield
    await drain_pending_appends()
    await app.state.audit_channel.close(grace=2)
    await app.state.auth_channel.close(grace=2)
    await app.state.alert_channel.close(grace=2)
    await app.state.inference_channel.close(grace=2)
    await app.state.broadcaster.stop()
    await close_redis(app.state.redis)
    await close_mongodb_connection()
    logger.info("backend stopped")
def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(NotFoundError)
    async def _not_found(_: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})
    @app.exception_handler(ConflictError)
    async def _conflict(_: Request, exc: ConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})
    @app.exception_handler(ValidationError)
    async def _validation(_: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})
    @app.exception_handler(InferenceUnavailable)
    async def _inference_unavailable(
        _: Request, exc: InferenceUnavailable
    ) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})
    @app.exception_handler(AlertUnavailable)
    async def _alert_unavailable(
        _: Request, exc: AlertUnavailable
    ) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})
    @app.exception_handler(AuthUnavailable)
    async def _auth_unavailable(
        _: Request, exc: AuthUnavailable
    ) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})
    @app.exception_handler(RateLimited)
    async def _rate_limited(_: Request, exc: RateLimited) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={"detail": "rate limit exceeded"},
            headers={"Retry-After": str(exc.retry_after)},
        )
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        logger.error("unhandled domain error: %s", exc)
        return JSONResponse(status_code=500, content={"detail": "internal error"})
app = FastAPI(
    title="theft-detection backend",
    version="2.0.0",
    lifespan=lifespan,
    dependencies=[Depends(csrf_protect)],
)
setup_observability(app, service_name="theft-backend")
register_error_handlers(app)

app.include_router(
    cameras.router, prefix="/api/v1", dependencies=[Depends(rate_limit)]
)
app.include_router(
    detections.router, prefix="/api/v1", dependencies=[Depends(rate_limit)]
)
app.include_router(
    alerts.router, prefix="/api/v1", dependencies=[Depends(rate_limit)]
)
app.include_router(
    stats.router, prefix="/api/v1", dependencies=[Depends(rate_limit)]
)
app.include_router(streams.router)
@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
