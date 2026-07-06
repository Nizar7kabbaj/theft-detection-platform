from celery.signals import worker_process_init
from app.shared.celery_app import celery_app
from app.worker.observability import setup_worker_observability

__all__ = ["celery_app"]


@worker_process_init.connect(weak=False)
def _init_worker(**_kwargs: object) -> None:
    setup_worker_observability()
