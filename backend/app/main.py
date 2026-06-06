import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.database import connect_to_mongodb, close_mongodb_connection
from .api.routes import cameras, detections, alerts, stats
from .observability import setup_observability

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("starting theft detection api")
    await connect_to_mongodb()
    logger.info("api ready")
    yield
    await close_mongodb_connection()
    logger.info("api shut down cleanly")


app = FastAPI(
    title="Theft Detection API",
    description="Real-Time AI Theft Detection Platform Backend API",
    version="1.0.0",
    lifespan=lifespan,
)

setup_observability(app, service_name="theft-backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cameras.router,    prefix="/api/cameras",    tags=["Cameras"])
app.include_router(detections.router, prefix="/api/detections", tags=["Detections"])
app.include_router(alerts.router,     prefix="/api/alerts",     tags=["Alerts"])
app.include_router(stats.router,      prefix="/api/stats",      tags=["Statistics"])


@app.get("/", tags=["Health"])
async def root():
    return {
        "status":  "running",
        "message": "Theft Detection API is online",
        "version": "1.0.0",
        "docs":    "/docs",
    }


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "healthy"}
