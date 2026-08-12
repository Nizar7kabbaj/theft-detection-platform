import logging
import os
import socket
from urllib.parse import urlsplit

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.pymongo import PymongoInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import start_http_server
from pythonjsonlogger.json import JsonFormatter


def setup_observability(app, service_name: str) -> None:
    resource = Resource.create({"service.name": service_name})

    tracer_provider = TracerProvider(resource=resource)
    exporting = _collector_reachable()
    if exporting:
        tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(tracer_provider)

    metric_reader = PrometheusMetricReader()
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[metric_reader]))
    start_http_server(port=int(os.getenv("PROMETHEUS_EXPORTER_PORT", "9464")))

    LoggingInstrumentor().instrument(set_logging_format=False)

    log_format = os.getenv(
        "OTEL_PYTHON_LOG_FORMAT",
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter(log_format))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    if not exporting:
        logging.getLogger(__name__).info("trace export disabled, collector not resolvable")

    FastAPIInstrumentor.instrument_app(app)
    PymongoInstrumentor().instrument()


def _collector_reachable() -> bool:
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    if not endpoint:
        return False
    host = urlsplit(endpoint).hostname
    if not host:
        return False
    try:
        socket.getaddrinfo(host, None)
    except OSError:
        return False
    return True
