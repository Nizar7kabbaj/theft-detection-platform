import ssl

from celery import Celery

from app.shared.config import settings

_ssl_options = (
    {
        "ssl_cert_reqs": ssl.CERT_REQUIRED,
        "ssl_ca_certs": str(settings.TLS_CA_FILE),
        "ssl_certfile": str(settings.TLS_CERT_FILE),
        "ssl_keyfile": str(settings.TLS_KEY_FILE),
    }
    if settings.REDIS_TLS
    else None
)

celery_app = Celery(
    "alerts",
    broker=settings.REDIS_URL,
    backend=settings.RESULT_BACKEND_URL,
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
    result_backend_transport_options={"global_keyprefix": "results:"},
    broker_use_ssl=_ssl_options,
    redis_backend_use_ssl=_ssl_options,
)


if settings.RECONCILER_ENABLED:
    celery_app.conf.beat_schedule = {
        "reconcile-stale-intents": {
            "task": "app.worker.tasks.reconcile_intents_task",
            "schedule": float(settings.RECONCILER_INTERVAL_SEC),
        },
    }

celery_app.conf.beat_schedule = {
    **getattr(celery_app.conf, "beat_schedule", {}),
    "probe-delivery-gate": {
        "task": "app.worker.tasks.probe_gate_task",
        "schedule": float(settings.GATE_PROBE_INTERVAL_SEC),
    },
}
