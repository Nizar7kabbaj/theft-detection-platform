from datetime import UTC, datetime, timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import NameOID

from app.grpc_gen import common_pb2
from app.grpc_server.identity import IdentityError, source_service_from_pem

PREFIX = "spiffe://theft-detection-platform/service/"


def _pem(uris: list[str] | None) -> bytes:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test")])
    now = datetime.now(UTC)
    builder = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
    )
    if uris is not None:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([x509.UniformResourceIdentifier(uri) for uri in uris]),
            critical=False,
        )
    return builder.sign(key, hashes.SHA256()).public_bytes(Encoding.PEM)


def test_one_known_identity_resolves() -> None:
    assert source_service_from_pem(_pem([PREFIX + "notification"])) == (
        common_pb2.SOURCE_SERVICE_NOTIFICATION
    )


@pytest.mark.parametrize(
    "uris",
    [
        None,
        [],
        [PREFIX + "notification", PREFIX + "api"],
        [PREFIX + "intruder"],
        ["spiffe://other-domain/service/notification"],
    ],
)
def test_anything_else_is_refused(uris: list[str] | None) -> None:
    with pytest.raises(IdentityError):
        source_service_from_pem(_pem(uris))


@pytest.mark.parametrize("pem", [b"", b"not a certificate"])
def test_missing_or_broken_certificates_are_refused(pem: bytes) -> None:
    with pytest.raises(IdentityError):
        source_service_from_pem(pem)
