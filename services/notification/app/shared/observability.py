from __future__ import annotations

import logging
import os

from opentelemetry import metrics, trace
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.propagate import extract, inject
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import start_http_server
from pythonjsonlogger.json import JsonFormatter

_WEBHOOK_DURATION_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


def setup_base(service_name: str) -> None:
    resource = Resource.create({"service.name": os.getenv("OTEL_SERVICE_NAME", service_name)})
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(tracer_provider)
    metric_reader = PrometheusMetricReader()
    views = [
        View(
            instrument_name="theft_alert_webhook_duration_seconds",
            aggregation=ExplicitBucketHistogramAggregation(_WEBHOOK_DURATION_BUCKETS),
        ),
    ]
    metrics.set_meter_provider(
        MeterProvider(resource=resource, metric_readers=[metric_reader], views=views)
    )
    start_http_server(port=int(os.getenv("PROMETHEUS_EXPORTER_PORT", "9464")))
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


def inject_context() -> dict[str, str]:
    carrier: dict[str, str] = {}
    inject(carrier)
    return carrier


def extract_context(carrier: dict[str, str]) -> Context:
    return extract(carrier)
