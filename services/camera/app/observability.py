import logging
import os
from collections.abc import Callable

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.instrumentation.grpc import GrpcAioInstrumentorClient
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.metrics import CallbackOptions, Observation
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import start_http_server
from pythonjsonlogger.json import JsonFormatter


def setup_observability(service_name: str) -> None:
    resource = Resource.create({"service.name": os.getenv("OTEL_SERVICE_NAME", service_name)})
    tracer_provider = TracerProvider(resource=resource)
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
    GrpcAioInstrumentorClient().instrument()


def register_capture_metrics(
    camera_id: str,
    buffer_counters: Callable[[], dict[str, int]],
    forward_counters: Callable[[], dict[str, int]],
    publish_counters: Callable[[], dict[str, int]],
    buffer_depth: Callable[[], int],
    target_fps: Callable[[], int],
) -> None:
    meter = metrics.get_meter("theft.camera")
    attrs = {"camera_id": camera_id}

    def _captured(options: CallbackOptions):
        yield Observation(buffer_counters()["captured_total"], attrs)

    def _dropped_overflow(options: CallbackOptions):
        yield Observation(buffer_counters()["dropped_overflow_total"], attrs)

    def _dropped_stale(options: CallbackOptions):
        yield Observation(buffer_counters()["dropped_stale_total"], attrs)

    def _forwarded(options: CallbackOptions):
        yield Observation(forward_counters()["forwarded_total"], attrs)

    def _failed(options: CallbackOptions):
        yield Observation(forward_counters()["failed_total"], attrs)

    def _published(options: CallbackOptions):
        yield Observation(publish_counters()["published_total"], attrs)

    def _publish_failed(options: CallbackOptions):
        yield Observation(publish_counters()["failed_total"], attrs)

    def _publish_dropped(options: CallbackOptions):
        yield Observation(publish_counters()["dropped_overflow_total"], attrs)

    def _publish_queue_depth(options: CallbackOptions):
        yield Observation(publish_counters()["queue_depth"], attrs)

    def _depth(options: CallbackOptions):
        yield Observation(buffer_depth(), attrs)

    def _target_fps(options: CallbackOptions):
        yield Observation(target_fps(), attrs)

    meter.create_observable_counter("theft_camera_frames_captured", callbacks=[_captured], unit="1")
    meter.create_observable_counter(
        "theft_camera_frames_dropped_overflow", callbacks=[_dropped_overflow], unit="1"
    )
    meter.create_observable_counter(
        "theft_camera_frames_dropped_stale", callbacks=[_dropped_stale], unit="1"
    )
    meter.create_observable_counter(
        "theft_camera_frames_forwarded", callbacks=[_forwarded], unit="1"
    )
    meter.create_observable_counter("theft_camera_frames_failed", callbacks=[_failed], unit="1")
    meter.create_observable_counter(
        "theft_camera_frames_published", callbacks=[_published], unit="1"
    )
    meter.create_observable_counter(
        "theft_camera_frames_publish_failed", callbacks=[_publish_failed], unit="1"
    )
    meter.create_observable_counter(
        "theft_camera_frames_publish_dropped", callbacks=[_publish_dropped], unit="1"
    )
    meter.create_observable_gauge(
        "theft_camera_publish_queue_depth", callbacks=[_publish_queue_depth], unit="1"
    )
    meter.create_observable_gauge("theft_camera_buffer_depth", callbacks=[_depth], unit="1")
    meter.create_observable_gauge("theft_camera_target_fps", callbacks=[_target_fps], unit="1")
