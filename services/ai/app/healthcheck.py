import sys

import grpc
from grpc_health.v1 import health_pb2, health_pb2_grpc

from app.core.config import settings


def main() -> int:
    service = sys.argv[1] if len(sys.argv) > 1 else "readiness"
    with grpc.insecure_channel(f"127.0.0.1:{settings.HEALTH_PORT}") as channel:
        try:
            reply = health_pb2_grpc.HealthStub(channel).Check(
                health_pb2.HealthCheckRequest(service=service), timeout=3
            )
        except grpc.RpcError:
            return 1
    return 0 if reply.status == health_pb2.HealthCheckResponse.SERVING else 1


if __name__ == "__main__":
    sys.exit(main())
