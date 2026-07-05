import asyncio

from celery.signals import worker_process_init

from app.core.database import (
    close_mongodb_connection,
    connect_to_mongodb,
    ensure_indexes,
)
from app.shared.celery_app import celery_app
from app.worker.observability import setup_worker_observability

__all__ = ["celery_app"]


async def _ensure_indexes() -> None:
    await connect_to_mongodb()
    try:
        await ensure_indexes()
    finally:
        await close_mongodb_connection()


@worker_process_init.connect(weak=False)
def _init_worker(**_kwargs: object) -> None:
    setup_worker_observability()
    asyncio.run(_ensure_indexes())
