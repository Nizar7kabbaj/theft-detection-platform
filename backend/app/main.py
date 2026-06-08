import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.v1 import alerts, cameras, detections, stats
from .core.database import (
    close_mongodb_connection,
    connect_to_mongodb,
    get_database,
)
from .core.errors import AppError, ConflictError, NotFoundError, ValidationError
from .observability import setup_observability

logger = logging.getLogger(__name__)


async def _create_indexes() -> None:
    db = get_database()
    await db.cameras.create_index("name", unique=True)
    await db.detections.create_index([("session_id", 1), ("timestamp", -1)])
    await db.alerts.create_index([("acknowledged", 1), ("created_at", -1)])
    logger.info("startup indexes ready")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("backend starting")
    await connect_to_mongodb()
    await _create_indexes()
    logger.info("backend ready")
    yield
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

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        logger.error("unhandled domain error: %s", exc)
        return JSONResponse(status_code=500, content={"detail": "internal error"})


app = FastAPI(
    title="theft-detection backend",
    version="2.0.0",
    lifespan=lifespan,
)

setup_observability(app, service_name="theft-backend")
register_error_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cameras.router, prefix="/api/v1")
app.include_router(detections.router, prefix="/api/v1")
app.include_router(alerts.router, prefix="/api/v1")
app.include_router(stats.router, prefix="/api/v1")


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
