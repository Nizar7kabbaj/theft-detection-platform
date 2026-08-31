from __future__ import annotations

import datetime as dt

import pytest
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import NameOID

from app.server import identity
from app.server.grpc_gen import common_pb2
from app.server.identity import (
    IdentityError,
    service_name,
    source_service_from_pem,
)

_TRUST_PREFIX = "spiffe://theft-detection-platform/service/"


def _certificate(uris: list[str], include_san: bool = True) -> x509.Certificate:
    key = Ed25519PrivateKey.generate()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "harness")])
    now = dt.datetime.now(dt.UTC)
    builder = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(hours=1))
    )
    if include_san:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([x509.UniformResourceIdentifier(uri) for uri in uris]),
            critical=False,
        )
    return builder.sign(key, None)


def _pem(uris: list[str], include_san: bool = True) -> bytes:
    return _certificate(uris, include_san).public_bytes(Encoding.PEM)


def test_known_service_identity_resolves():
    pem = _pem([f"{_TRUST_PREFIX}api"])

    assert source_service_from_pem(pem) == common_pb2.SOURCE_SERVICE_API


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("api", common_pb2.SOURCE_SERVICE_API),
        ("auth", common_pb2.SOURCE_SERVICE_AUTH),
        ("ai", common_pb2.SOURCE_SERVICE_AI),
        ("camera", common_pb2.SOURCE_SERVICE_CAMERA),
        ("detect-gate", common_pb2.SOURCE_SERVICE_DETECT_GATE),
        ("notification", common_pb2.SOURCE_SERVICE_NOTIFICATION),
        ("audit", common_pb2.SOURCE_SERVICE_AUDIT),
    ],
)
def test_every_known_service_name_maps(name: str, expected: int):
    assert source_service_from_pem(_pem([f"{_TRUST_PREFIX}{name}"])) == expected


def test_empty_pem_is_rejected():
    with pytest.raises(IdentityError, match="no certificate"):
        source_service_from_pem(b"")


def test_unparseable_pem_is_rejected():
    with pytest.raises(IdentityError, match="not parseable"):
        source_service_from_pem(b"-----BEGIN CERTIFICATE-----\nnope\n-----END CERTIFICATE-----\n")


def test_certificate_without_san_is_rejected():
    with pytest.raises(IdentityError, match="subject alternative name"):
        source_service_from_pem(_pem([], include_san=False))


def test_certificate_with_no_trust_domain_uri_is_rejected():
    with pytest.raises(IdentityError, match="exactly one"):
        source_service_from_pem(_pem(["https://example.invalid/service/api"]))


def test_certificate_with_two_service_uris_is_rejected():
    pem = _pem([f"{_TRUST_PREFIX}api", f"{_TRUST_PREFIX}auth"])

    with pytest.raises(IdentityError, match="exactly one"):
        source_service_from_pem(pem)


def test_unknown_service_name_is_rejected():
    with pytest.raises(IdentityError, match="not a known service"):
        source_service_from_pem(_pem([f"{_TRUST_PREFIX}rogue"]))


def test_foreign_trust_domain_is_rejected():
    pem = _pem(["spiffe://other-domain/service/api"])

    with pytest.raises(IdentityError, match="exactly one"):
        source_service_from_pem(pem)


def test_unrelated_uris_alongside_service_uri_are_ignored():
    pem = _pem(["https://example.invalid/", f"{_TRUST_PREFIX}audit"])

    assert source_service_from_pem(pem) == common_pb2.SOURCE_SERVICE_AUDIT


def test_result_is_cached_by_certificate():
    certificate = _certificate([f"{_TRUST_PREFIX}api"])
    pem = certificate.public_bytes(Encoding.PEM)
    source_service_from_pem(pem)

    identity._cache[certificate.public_bytes(Encoding.DER)] = common_pb2.SOURCE_SERVICE_CAMERA

    assert source_service_from_pem(pem) == common_pb2.SOURCE_SERVICE_CAMERA


def test_cache_is_cleared_when_limit_is_reached():
    for index in range(identity._CACHE_LIMIT):
        identity._cache[index.to_bytes(4, "big")] = common_pb2.SOURCE_SERVICE_API

    source_service_from_pem(_pem([f"{_TRUST_PREFIX}auth"]))

    assert len(identity._cache) == 1


def test_service_name_round_trips():
    assert service_name(common_pb2.SOURCE_SERVICE_AUTH) == "auth"
    assert service_name(common_pb2.SOURCE_SERVICE_DETECT_GATE) == "detect-gate"


def test_service_name_falls_back_for_unknown_value():
    assert service_name(9999) == "unknown"
