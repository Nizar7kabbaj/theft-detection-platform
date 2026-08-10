from __future__ import annotations

from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import ExtensionOID

from app.server.grpc_gen import common_pb2

TRUST_DOMAIN = "theft-detection-platform"
_URI_PREFIX = f"spiffe://{TRUST_DOMAIN}/service/"

_SERVICE_BY_NAME = {
    "api": common_pb2.SOURCE_SERVICE_API,
    "auth": common_pb2.SOURCE_SERVICE_AUTH,
    "ai": common_pb2.SOURCE_SERVICE_AI,
    "camera": common_pb2.SOURCE_SERVICE_CAMERA,
    "detect-gate": common_pb2.SOURCE_SERVICE_DETECT_GATE,
    "notification": common_pb2.SOURCE_SERVICE_NOTIFICATION,
    "audit": common_pb2.SOURCE_SERVICE_AUDIT,
}

_CACHE_LIMIT = 64
_cache: dict[bytes, int] = {}


class IdentityError(Exception):
    pass


def _uri_sans(certificate: x509.Certificate) -> list[str]:
    try:
        extension = certificate.extensions.get_extension_for_oid(
            ExtensionOID.SUBJECT_ALTERNATIVE_NAME
        )
    except x509.ExtensionNotFound as exc:
        raise IdentityError("certificate carries no subject alternative name") from exc
    return [
        value
        for value in extension.value.get_values_for_type(x509.UniformResourceIdentifier)
        if value.startswith(_URI_PREFIX)
    ]


def _resolve(certificate: x509.Certificate) -> int:
    uris = _uri_sans(certificate)
    if len(uris) != 1:
        raise IdentityError("certificate must carry exactly one service identity")
    name = uris[0].removeprefix(_URI_PREFIX)
    if name not in _SERVICE_BY_NAME:
        raise IdentityError("certificate identity is not a known service")
    return _SERVICE_BY_NAME[name]


def source_service_from_pem(pem: bytes) -> int:
    if not pem:
        raise IdentityError("peer presented no certificate")
    try:
        certificate = x509.load_pem_x509_certificate(pem)
    except ValueError as exc:
        raise IdentityError("peer certificate is not parseable") from exc
    key = certificate.public_bytes(Encoding.DER)
    cached = _cache.get(key)
    if cached is not None:
        return cached
    resolved = _resolve(certificate)
    if len(_cache) >= _CACHE_LIMIT:
        _cache.clear()
    _cache[key] = resolved
    return resolved


def service_name(source_service: int) -> str:
    for name, value in _SERVICE_BY_NAME.items():
        if value == source_service:
            return name
    return "unknown"
