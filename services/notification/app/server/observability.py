from opentelemetry.instrumentation.grpc import GrpcAioInstrumentorServer
from opentelemetry.instrumentation.logging import LoggingInstrumentor

from app.shared.observability import setup_base


def setup_server_observability() -> None:
    setup_base(service_name="notification")
    LoggingInstrumentor().instrument(set_logging_format=False)
    GrpcAioInstrumentorServer().instrument()
