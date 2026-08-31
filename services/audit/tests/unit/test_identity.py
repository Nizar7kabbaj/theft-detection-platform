from __future__ import annotations

import pytest

from app.server import identity
from app.server.grpc_gen import common_pb2
from tests.conftest import make_service_certificate

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("service_name", "expected"),
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
def test_each_known_service_resolves(service_name: str, expected: int) -> None:
    pem = make_service_certificate(service_name)
    assert identity.source_service_from_pem(pem) == expected


def test_empty_pem_is_rejected() -> None:
    with pytest.raises(identity.IdentityError, match="peer presented no certificate"):
        identity.source_service_from_pem(b"")


def test_unparseable_pem_is_rejected() -> None:
    with pytest.raises(identity.IdentityError, match="not parseable"):
        identity.source_service_from_pem(b"-----BEGIN CERTIFICATE-----\nnope\n")


def test_certificate_without_san_is_rejected() -> None:
    pem = make_service_certificate("api", include_san=False)
    with pytest.raises(identity.IdentityError, match="no subject alternative name"):
        identity.source_service_from_pem(pem)


def test_certificate_with_no_matching_uri_is_rejected() -> None:
    pem = make_service_certificate(None, extra_uris=("https://example.invalid/api",))
    with pytest.raises(identity.IdentityError, match="exactly one service identity"):
        identity.source_service_from_pem(pem)


def test_certificate_with_two_service_identities_is_rejected() -> None:
    pem = make_service_certificate(
        "api",
        extra_uris=(f"spiffe://{identity.TRUST_DOMAIN}/service/auth",),
    )
    with pytest.raises(identity.IdentityError, match="exactly one service identity"):
        identity.source_service_from_pem(pem)


def test_certificate_from_another_trust_domain_is_rejected() -> None:
    pem = make_service_certificate("api", trust_domain="attacker-platform")
    with pytest.raises(identity.IdentityError, match="exactly one service identity"):
        identity.source_service_from_pem(pem)


def test_trust_domain_prefix_must_match_exactly() -> None:
    pem = make_service_certificate("api", trust_domain=f"{identity.TRUST_DOMAIN}-evil")
    with pytest.raises(identity.IdentityError, match="exactly one service identity"):
        identity.source_service_from_pem(pem)


def test_unknown_service_name_is_rejected() -> None:
    pem = make_service_certificate("billing")
    with pytest.raises(identity.IdentityError, match="not a known service"):
        identity.source_service_from_pem(pem)


def test_empty_service_name_is_rejected() -> None:
    pem = make_service_certificate("")
    with pytest.raises(identity.IdentityError, match="not a known service"):
        identity.source_service_from_pem(pem)


def test_service_name_is_case_sensitive() -> None:
    pem = make_service_certificate("API")
    with pytest.raises(identity.IdentityError, match="not a known service"):
        identity.source_service_from_pem(pem)


def test_path_traversal_in_service_name_is_rejected() -> None:
    pem = make_service_certificate("api/../auth")
    with pytest.raises(identity.IdentityError, match="not a known service"):
        identity.source_service_from_pem(pem)


def test_unrelated_uri_alongside_service_identity_is_ignored() -> None:
    pem = make_service_certificate("api", extra_uris=("https://example.invalid/health",))
    assert identity.source_service_from_pem(pem) == common_pb2.SOURCE_SERVICE_API


def test_common_name_does_not_influence_resolution() -> None:
    pem = make_service_certificate("api", common_name="auth")
    assert identity.source_service_from_pem(pem) == common_pb2.SOURCE_SERVICE_API


def test_result_is_cached_by_certificate() -> None:
    pem = make_service_certificate("api")
    identity.source_service_from_pem(pem)
    assert len(identity._cache) == 1
    identity.source_service_from_pem(pem)
    assert len(identity._cache) == 1


def test_distinct_certificates_occupy_distinct_cache_entries() -> None:
    first = make_service_certificate("api")
    second = make_service_certificate("auth")
    assert identity.source_service_from_pem(first) == common_pb2.SOURCE_SERVICE_API
    assert identity.source_service_from_pem(second) == common_pb2.SOURCE_SERVICE_AUTH
    assert len(identity._cache) == 2


def test_cache_clears_when_limit_is_reached() -> None:
    for _ in range(identity._CACHE_LIMIT):
        identity.source_service_from_pem(make_service_certificate("api"))
    assert len(identity._cache) == identity._CACHE_LIMIT
    identity.source_service_from_pem(make_service_certificate("auth"))
    assert len(identity._cache) == 1


def test_rejected_certificate_is_not_cached() -> None:
    pem = make_service_certificate("billing")
    with pytest.raises(identity.IdentityError):
        identity.source_service_from_pem(pem)
    assert len(identity._cache) == 0


@pytest.mark.parametrize(
    ("source_service", "expected"),
    [
        (common_pb2.SOURCE_SERVICE_API, "api"),
        (common_pb2.SOURCE_SERVICE_AUTH, "auth"),
        (common_pb2.SOURCE_SERVICE_AUDIT, "audit"),
        (common_pb2.SOURCE_SERVICE_UNSPECIFIED, "unknown"),
        (99, "unknown"),
    ],
)
def test_service_name_round_trip(source_service: int, expected: str) -> None:
    assert identity.service_name(source_service) == expected
