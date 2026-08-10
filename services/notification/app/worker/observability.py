import re

from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.trace import Span
from requests import PreparedRequest

from app.shared.observability import setup_base

_TELEGRAM_TOKEN_URL = re.compile(r"/bot[^/]+/")


def _redact_telegram_url(span: Span, request: PreparedRequest) -> None:
    if not span.is_recording():
        return
    url = request.url or ""
    if "api.telegram.org" not in url:
        return
    scrubbed = _TELEGRAM_TOKEN_URL.sub("/bot<redacted>/", url)
    span.set_attribute("url.full", scrubbed)
    span.set_attribute("http.url", scrubbed)


def setup_worker_observability() -> None:
    setup_base(service_name="notification-worker")
    LoggingInstrumentor().instrument(set_logging_format=False)
    CeleryInstrumentor().instrument()
    RequestsInstrumentor().instrument(request_hook=_redact_telegram_url)
