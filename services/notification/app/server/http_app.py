import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.server.api.webhooks import router as webhooks_router

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="notification-service http",
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
    )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error in http handler: %s", exc)
        return JSONResponse(status_code=500, content={"detail": "internal error"})

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(webhooks_router)

    return app
