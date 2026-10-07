import re

from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor, RequestInfo
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.trace import Span

from app.shared.observability import setup_base

_TELEGRAM_TOKEN_URL = re.compile(r"/bot[^/]+/")


def _redact_telegram_url(span: Span, request: RequestInfo) -> None:
    if not span.is_recording():
        return
    url = str(request.url)
    if "api.telegram.org" not in url:
        return
    scrubbed = _TELEGRAM_TOKEN_URL.sub("/bot<redacted>/", url)
    span.set_attribute("url.full", scrubbed)
    span.set_attribute("http.url", scrubbed)


async def _redact_telegram_url_async(span: Span, request: RequestInfo) -> None:
    _redact_telegram_url(span, request)


def instrument_telegram_http() -> None:
    HTTPXClientInstrumentor().instrument(
        request_hook=_redact_telegram_url,
        async_request_hook=_redact_telegram_url_async,
    )


def setup_worker_observability() -> None:
    setup_base(service_name="notification-worker")
    LoggingInstrumentor().instrument(set_logging_format=False)
    CeleryInstrumentor().instrument()
    instrument_telegram_http()
