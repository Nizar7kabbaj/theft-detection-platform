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


def register_gate_metrics(
    camera_id: str,
    presence_value: Callable[[], int],
    gate_counters: Callable[[], dict[str, int]],
    stream_counters: Callable[[], dict[str, int]],
) -> None:
    meter = metrics.get_meter("theft.detect_gate")
    attrs = {"camera_id": camera_id}

    def _presence(options: CallbackOptions):
        yield Observation(presence_value(), attrs)

    def _frames_processed(options: CallbackOptions):
        yield Observation(gate_counters()["frames_processed_total"], attrs)

    def _person_detections(options: CallbackOptions):
        yield Observation(gate_counters()["person_detections_total"], attrs)

    def _entries(options: CallbackOptions):
        yield Observation(gate_counters()["entries_total"], attrs)

    def _exits(options: CallbackOptions):
        yield Observation(gate_counters()["exits_total"], attrs)

    def _events_sent(options: CallbackOptions):
        yield Observation(stream_counters()["events_sent_total"], attrs)

    def _acks_received(options: CallbackOptions):
        yield Observation(stream_counters()["acks_received_total"], attrs)

    def _stream_failures(options: CallbackOptions):
        yield Observation(stream_counters()["stream_failures_total"], attrs)

    meter.create_observable_gauge(
        "theft_detect_gate_presence_state", callbacks=[_presence], unit="1"
    )
    meter.create_observable_counter(
        "theft_detect_gate_frames_processed", callbacks=[_frames_processed], unit="1"
    )
    meter.create_observable_counter(
        "theft_detect_gate_person_detections", callbacks=[_person_detections], unit="1"
    )
    meter.create_observable_counter("theft_detect_gate_entries", callbacks=[_entries], unit="1")
    meter.create_observable_counter("theft_detect_gate_exits", callbacks=[_exits], unit="1")
    meter.create_observable_counter(
        "theft_detect_gate_events_sent", callbacks=[_events_sent], unit="1"
    )
    meter.create_observable_counter(
        "theft_detect_gate_acks_received", callbacks=[_acks_received], unit="1"
    )
    meter.create_observable_counter(
        "theft_detect_gate_stream_failures", callbacks=[_stream_failures], unit="1"
    )
