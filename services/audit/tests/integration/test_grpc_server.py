from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import grpc
import pytest
import pytest_asyncio
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)
from cryptography.x509.oid import NameOID

from app.server import identity as identity_module
from app.server.grpc_gen import audit_pb2, audit_pb2_grpc, common_pb2
from app.server.interceptors import IdentityInterceptor
from app.server.servicer import AuditServicer

pytestmark = pytest.mark.integration


def _key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _pem(key) -> bytes:
    return key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())


def build_ca() -> tuple[x509.Certificate, object]:
    key = _key()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test-ca")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    return certificate, key


def issue(ca_certificate, ca_key, service_name: str | None, common_name: str = "peer"):
    key = _key()
    now = datetime.now(UTC)
    builder = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)]))
        .issuer_name(ca_certificate.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=1))
    )
    names: list[x509.GeneralName] = [x509.DNSName("localhost")]
    if service_name is not None:
        names.append(
            x509.UniformResourceIdentifier(
                f"spiffe://{identity_module.TRUST_DOMAIN}/service/{service_name}"
            )
        )
    builder = builder.add_extension(x509.SubjectAlternativeName(names), critical=False)
    certificate = builder.sign(ca_key, hashes.SHA256())
    return certificate.public_bytes(Encoding.PEM), _pem(key)


@pytest_asyncio.fixture
async def secure_server(database_settings: None) -> AsyncIterator[dict]:
    ca_certificate, ca_key = build_ca()
    ca_pem = ca_certificate.public_bytes(Encoding.PEM)
    server_pem, server_key = issue(ca_certificate, ca_key, "audit", common_name="localhost")
    credentials = grpc.ssl_server_credentials(
        [(server_key, server_pem)],
        root_certificates=ca_pem,
        require_client_auth=True,
    )
    server = grpc.aio.server(interceptors=[IdentityInterceptor()])
    audit_pb2_grpc.add_AuditServiceServicer_to_server(AuditServicer(), server)
    port = server.add_secure_port("127.0.0.1:0", credentials)
    await server.start()
    try:
        yield {
            "port": port,
            "ca_pem": ca_pem,
            "ca_certificate": ca_certificate,
            "ca_key": ca_key,
        }
    finally:
        await server.stop(None)


def channel_for(secure_server: dict, service_name: str | None):
    client_pem, client_key = issue(
        secure_server["ca_certificate"], secure_server["ca_key"], service_name
    )
    credentials = grpc.ssl_channel_credentials(
        root_certificates=secure_server["ca_pem"],
        private_key=client_key,
        certificate_chain=client_pem,
    )
    return grpc.aio.secure_channel(
        f"127.0.0.1:{secure_server['port']}",
        credentials,
        options=(("grpc.ssl_target_name_override", "localhost"),),
    )


def make_event(source_service: int, **overrides) -> audit_pb2.AuditEvent:
    event = audit_pb2.AuditEvent(
        schema_version=overrides.get("schema_version", 1),
        event_id=overrides.get("event_id", str(uuid.uuid4())),
        source_service=source_service,
        actor=overrides.get("actor", "actor-1"),
        severity=common_pb2.SEVERITY_INFO,
    )
    event.occurred_at.FromDatetime(overrides.get("occurred_at", datetime.now(UTC)))
    event.service_lifecycle.version = "0.1.0"
    return event


@pytest.fixture
def unlimited_rate(monkeypatch: pytest.MonkeyPatch) -> None:
    async def allow(source_service: int) -> bool:
        return True

    monkeypatch.setattr("app.server.servicer.check_append_rate", allow)


async def test_an_authenticated_service_can_append(secure_server, unlimited_rate) -> None:
    async with channel_for(secure_server, "auth") as channel:
        stub = audit_pb2_grpc.AuditServiceStub(channel)
        reply = await stub.AppendEvent(make_event(common_pb2.SOURCE_SERVICE_AUTH))
    assert reply.status == audit_pb2.APPEND_STATUS_ACCEPTED
    assert reply.sequence_number == "1"


async def test_the_append_reply_carries_the_chain_hashes(secure_server, unlimited_rate) -> None:
    async with channel_for(secure_server, "auth") as channel:
        stub = audit_pb2_grpc.AuditServiceStub(channel)
        reply = await stub.AppendEvent(make_event(common_pb2.SOURCE_SERVICE_AUTH))
    assert len(reply.chain_hash) == 32
    assert len(reply.leaf_hash) == 32


async def test_a_caller_cannot_append_as_another_service(secure_server, unlimited_rate) -> None:
    async with channel_for(secure_server, "auth") as channel:
        stub = audit_pb2_grpc.AuditServiceStub(channel)
        reply = await stub.AppendEvent(make_event(common_pb2.SOURCE_SERVICE_API))
    assert reply.status == audit_pb2.APPEND_STATUS_REJECTED


async def test_a_certificate_without_a_service_identity_is_refused(
    secure_server, unlimited_rate
) -> None:
    async with channel_for(secure_server, None) as channel:
        stub = audit_pb2_grpc.AuditServiceStub(channel)
        with pytest.raises(grpc.aio.AioRpcError) as excinfo:
            await stub.AppendEvent(make_event(common_pb2.SOURCE_SERVICE_AUTH))
    assert excinfo.value.code() == grpc.StatusCode.UNAUTHENTICATED


async def test_an_unidentified_caller_cannot_append_as_unspecified(
    secure_server, unlimited_rate
) -> None:
    async with channel_for(secure_server, None) as channel:
        stub = audit_pb2_grpc.AuditServiceStub(channel)
        with pytest.raises(grpc.aio.AioRpcError) as excinfo:
            await stub.AppendEvent(make_event(common_pb2.SOURCE_SERVICE_UNSPECIFIED))
    assert excinfo.value.code() == grpc.StatusCode.UNAUTHENTICATED


async def test_a_client_without_a_certificate_cannot_connect(secure_server) -> None:
    credentials = grpc.ssl_channel_credentials(root_certificates=secure_server["ca_pem"])
    async with grpc.aio.secure_channel(
        f"127.0.0.1:{secure_server['port']}",
        credentials,
        options=(("grpc.ssl_target_name_override", "localhost"),),
    ) as channel:
        stub = audit_pb2_grpc.AuditServiceStub(channel)
        with pytest.raises(grpc.aio.AioRpcError):
            await stub.AppendEvent(make_event(common_pb2.SOURCE_SERVICE_AUTH))


async def test_a_certificate_from_another_authority_is_refused(secure_server) -> None:
    foreign_ca, foreign_key = build_ca()
    client_pem, client_key = issue(foreign_ca, foreign_key, "auth")
    credentials = grpc.ssl_channel_credentials(
        root_certificates=secure_server["ca_pem"],
        private_key=client_key,
        certificate_chain=client_pem,
    )
    async with grpc.aio.secure_channel(
        f"127.0.0.1:{secure_server['port']}",
        credentials,
        options=(("grpc.ssl_target_name_override", "localhost"),),
    ) as channel:
        stub = audit_pb2_grpc.AuditServiceStub(channel)
        with pytest.raises(grpc.aio.AioRpcError):
            await stub.AppendEvent(make_event(common_pb2.SOURCE_SERVICE_AUTH))


async def test_an_unknown_service_identity_is_refused(secure_server, unlimited_rate) -> None:
    async with channel_for(secure_server, "billing") as channel:
        stub = audit_pb2_grpc.AuditServiceStub(channel)
        with pytest.raises(grpc.aio.AioRpcError) as excinfo:
            await stub.AppendEvent(make_event(common_pb2.SOURCE_SERVICE_AUTH))
    assert excinfo.value.code() == grpc.StatusCode.UNAUTHENTICATED


async def test_a_malformed_event_id_is_rejected_over_the_wire(
    secure_server, unlimited_rate
) -> None:
    async with channel_for(secure_server, "auth") as channel:
        stub = audit_pb2_grpc.AuditServiceStub(channel)
        reply = await stub.AppendEvent(
            make_event(common_pb2.SOURCE_SERVICE_AUTH, event_id="not-a-uuid")
        )
    assert reply.status == audit_pb2.APPEND_STATUS_REJECTED


async def test_a_future_schema_version_is_refused_over_the_wire(
    secure_server, unlimited_rate
) -> None:
    async with channel_for(secure_server, "auth") as channel:
        stub = audit_pb2_grpc.AuditServiceStub(channel)
        reply = await stub.AppendEvent(make_event(common_pb2.SOURCE_SERVICE_AUTH, schema_version=9))
    assert reply.status == audit_pb2.APPEND_STATUS_SCHEMA_UNSUPPORTED


async def test_appended_events_can_be_queried_back(secure_server, unlimited_rate) -> None:
    async with channel_for(secure_server, "auth") as channel:
        stub = audit_pb2_grpc.AuditServiceStub(channel)
        await stub.AppendEvent(make_event(common_pb2.SOURCE_SERVICE_AUTH, actor="nizar"))
        reply = await stub.QueryEvents(audit_pb2.QueryEventsRequest(actor="nizar"))
    assert len(reply.events) == 1
    assert reply.events[0].event.actor == "nizar"


async def test_a_query_records_its_own_access(secure_server, unlimited_rate) -> None:
    async with channel_for(secure_server, "auth") as channel:
        stub = audit_pb2_grpc.AuditServiceStub(channel)
        await stub.AppendEvent(make_event(common_pb2.SOURCE_SERVICE_AUTH))
        await stub.QueryEvents(audit_pb2.QueryEventsRequest())
        reply = await stub.QueryEvents(audit_pb2.QueryEventsRequest())
    kinds = [entry.event.WhichOneof("payload") for entry in reply.events]
    assert "audit_log_accessed" in kinds


async def test_a_malformed_page_token_is_refused_over_the_wire(
    secure_server, unlimited_rate
) -> None:
    async with channel_for(secure_server, "auth") as channel:
        stub = audit_pb2_grpc.AuditServiceStub(channel)
        with pytest.raises(grpc.aio.AioRpcError) as excinfo:
            await stub.QueryEvents(audit_pb2.QueryEventsRequest(page_token="abc"))
    assert excinfo.value.code() == grpc.StatusCode.INVALID_ARGUMENT


async def test_the_chain_verifies_over_the_wire(secure_server, unlimited_rate) -> None:
    async with channel_for(secure_server, "auth") as channel:
        stub = audit_pb2_grpc.AuditServiceStub(channel)
        for _ in range(3):
            await stub.AppendEvent(make_event(common_pb2.SOURCE_SERVICE_AUTH))
        reply = await stub.VerifyChain(audit_pb2.VerifyChainRequest())
    assert reply.chain_intact is True
    assert reply.events_verified >= 3


async def test_a_malformed_verify_range_is_refused_over_the_wire(
    secure_server, unlimited_rate
) -> None:
    async with channel_for(secure_server, "auth") as channel:
        stub = audit_pb2_grpc.AuditServiceStub(channel)
        with pytest.raises(grpc.aio.AioRpcError) as excinfo:
            await stub.VerifyChain(audit_pb2.VerifyChainRequest(from_sequence_number="x"))
    assert excinfo.value.code() == grpc.StatusCode.INVALID_ARGUMENT


async def test_an_absent_checkpoint_is_reported_over_the_wire(
    secure_server, unlimited_rate
) -> None:
    async with channel_for(secure_server, "auth") as channel:
        stub = audit_pb2_grpc.AuditServiceStub(channel)
        reply = await stub.GetCheckpoint(audit_pb2.GetCheckpointRequest())
    assert reply.found is False


async def test_a_second_service_appends_to_the_same_chain(secure_server, unlimited_rate) -> None:
    async with channel_for(secure_server, "auth") as channel:
        stub = audit_pb2_grpc.AuditServiceStub(channel)
        first = await stub.AppendEvent(make_event(common_pb2.SOURCE_SERVICE_AUTH))
    async with channel_for(secure_server, "api") as channel:
        stub = audit_pb2_grpc.AuditServiceStub(channel)
        second = await stub.AppendEvent(make_event(common_pb2.SOURCE_SERVICE_API))
    assert int(second.sequence_number) > int(first.sequence_number)
