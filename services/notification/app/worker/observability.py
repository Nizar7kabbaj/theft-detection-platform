from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor

from app.shared.observability import setup_base


def setup_worker_observability() -> None:
    setup_base(service_name="notification-worker")
    LoggingInstrumentor().instrument(set_logging_format=False)
    CeleryInstrumentor().instrument()
    RequestsInstrumentor().instrument()
