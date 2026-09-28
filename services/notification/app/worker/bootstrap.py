import signal

from celery.signals import worker_process_init

from app.shared.celery_app import celery_app
from app.shared.telegram_service import _token
from app.worker.heartbeat import HeartbeatStep
from app.worker.observability import setup_worker_observability

__all__ = ["celery_app"]

celery_app.steps["consumer"].add(HeartbeatStep)
celery_app.conf.beat_scheduler = "app.worker.heartbeat:HeartbeatScheduler"
celery_app.conf.beat_max_loop_interval = 30


def _reload_token(_signum: int, _frame: object) -> None:
    _token.cache_clear()


@worker_process_init.connect(weak=False)
def _init_worker(**_kwargs: object) -> None:
    setup_worker_observability()
    signal.signal(signal.SIGHUP, _reload_token)
