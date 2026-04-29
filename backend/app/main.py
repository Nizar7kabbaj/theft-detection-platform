"""
main.py — FastAPI application entry point
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from .core.database import connect_to_mongodb, close_mongodb_connection
from .api.routes import cameras, detections, alerts, stats

# ── Create FastAPI app ─────────────────────────────────────────────────────────

app = FastAPI(
    title="Theft Detection API",
    description="Real-Time AI Theft Detection Platform — Backend API",
    version="1.0.0",
)

# ── CORS Middleware ────────────────────────────────────────────────────────────
# Allows frontend to call the API

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Startup and shutdown events ────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    logger.info("Starting Theft Detection API...")
    await connect_to_mongodb()
    logger.success("API is ready")


@app.on_event("shutdown")
async def shutdown():
    await close_mongodb_connection()
    logger.info("API shut down cleanly")

# ── Include routers ────────────────────────────────────────────────────────────

app.include_router(cameras.router,    prefix="/api/cameras",    tags=["Cameras"])
app.include_router(detections.router, prefix="/api/detections", tags=["Detections"])
app.include_router(alerts.router,     prefix="/api/alerts",     tags=["Alerts"])
app.include_router(stats.router,      prefix="/api/stats",      tags=["Statistics"])

# ── Health check ───────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
async def root():
    return {
        "status":  "running",
        "message": "Theft Detection API is online",
        "version": "1.0.0",
        "docs":    "/docs"
    }


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "healthy"}