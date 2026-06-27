from celery import Celery
from celery.signals import worker_process_init

from app.core.config import settings
from app.observability import setup_observability

celery_app = Celery(
    "alerts",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks"],
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


@worker_process_init.connect(weak=False)
def _init_tracing(**_kwargs: object) -> None:
    setup_observability(service_name="theft-alert")
