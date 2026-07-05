from celery import Celery

from app.shared.config import settings

celery_app = Celery(
    "alerts",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
)

if settings.RECONCILER_ENABLED:
    celery_app.conf.beat_schedule = {
        "reconcile-stale-intents": {
            "task": "app.worker.tasks.reconcile_intents_task",
            "schedule": float(settings.RECONCILER_INTERVAL_SEC),
        },
    }
