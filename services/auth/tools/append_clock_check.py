from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from datetime import UTC, datetime, timedelta

import grpc

from app.core.config import get_settings
from app.server.grpc_gen import audit_pb2 as pb
from app.server.grpc_gen import common_pb2
from app.server.grpc_gen.audit_pb2_grpc import AuditServiceStub

_STATUS_NAMES = {
    pb.APPEND_STATUS_UNSPECIFIED: "unspecified",
    pb.APPEND_STATUS_ACCEPTED: "accepted",
    pb.APPEND_STATUS_REJECTED: "rejected",
    pb.APPEND_STATUS_RATE_LIMITED: "rate_limited",
    pb.APPEND_STATUS_SCHEMA_UNSUPPORTED: "schema_unsupported",
}


def _build_event(age_seconds: int) -> pb.AuditEvent:
    event = pb.AuditEvent(
        schema_version=1,
        event_id=str(uuid.uuid4()),
        source_service=common_pb2.SOURCE_SERVICE_AUTH,
        actor="",
        severity=common_pb2.SEVERITY_INFO,
    )
    event.occurred_at.FromDatetime(datetime.now(UTC) - timedelta(seconds=age_seconds))
    event.service_lifecycle.service = common_pb2.SOURCE_SERVICE_AUTH
    event.service_lifecycle.event_kind = pb.LIFECYCLE_EVENT_KIND_STARTED
    event.service_lifecycle.version = "0.1.0"
    return event


def _open_channel() -> grpc.aio.Channel:
    settings = get_settings()
    credentials = grpc.ssl_channel_credentials(
        root_certificates=settings.tls_ca_file.read_bytes(),
        private_key=settings.tls_key_file.read_bytes(),
        certificate_chain=settings.tls_cert_file.read_bytes(),
    )
    return grpc.aio.secure_channel(settings.audit_target, credentials)


async def _send(stub: AuditServiceStub, label: str, age_seconds: int, expected: int) -> bool:
    event = _build_event(age_seconds)
    try:
        reply = await stub.AppendEvent(event, timeout=10.0)
    except grpc.aio.AioRpcError as exc:
        print(f"{label:<12} transport error {exc.code().name}")
        return False
    observed = _STATUS_NAMES.get(reply.status, str(reply.status))
    wanted = _STATUS_NAMES.get(expected, str(expected))
    ok = reply.status == expected
    sequence = reply.sequence_number or "-"
    print(
        f"{label:<12} expected {wanted:<10} observed {observed:<10} "
        f"sequence {sequence:<8} {'pass' if ok else 'fail'}"
    )
    if ok and reply.status == pb.APPEND_STATUS_ACCEPTED:
        print(f"{'':<12} event_id {event.event_id}")
    return ok


async def _run() -> int:
    cases = (
        ("now", 0, pb.APPEND_STATUS_ACCEPTED),
        ("3 days", 3 * 86400, pb.APPEND_STATUS_ACCEPTED),
        ("8 days", 8 * 86400, pb.APPEND_STATUS_REJECTED),
    )
    channel = _open_channel()
    try:
        stub = AuditServiceStub(channel)
        results = [await _send(stub, label, age, expected) for label, age, expected in cases]
    finally:
        await channel.close(grace=2)
    passed = sum(1 for entry in results if entry)
    print(f"\n{passed} of {len(results)} cases passed")
    return 0 if passed == len(results) else 1


def main() -> None:
    argparse.ArgumentParser(prog="append-clock-check").parse_args()
    sys.exit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
