from __future__ import annotations

import datetime as _datetime
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field

import grpc
import pytest
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import NameOID

from app.core import database as database_module
from app.core import pseudonym as pseudonym_module
from app.core import redis as redis_module
from app.core import signing as signing_module
from app.core.config import get_settings
from app.server import identity as identity_module


def reset_caches() -> None:
    get_settings.cache_clear()
    signing_module.reset_signer_cache()
    pseudonym_module.reset_cache()
    database_module._load_password.cache_clear()
    database_module._engine = None
    database_module._sessionmaker = None
    database_module._owner_engine = None
    database_module._owner_sessionmaker = None
    redis_module._load_redis_password.cache_clear()
    redis_module._client = None
    identity_module._cache.clear()


@pytest.fixture(autouse=True)
def reset_module_state() -> Iterator[None]:
    reset_caches()
    yield
    reset_caches()


class AbortError(Exception):
    code: grpc.StatusCode
    details: str

    def __init__(self, code: grpc.StatusCode, details: str) -> None:
        super().__init__(details)
        self.code = code
        self.details = details


@dataclass
class FakeServicerContext:
    invocation_metadata_value: tuple = ()
    peer_certificate: bytes = b""
    aborted: AbortError | None = field(default=None, init=False)

    async def abort(self, code, details: str):
        self.aborted = AbortError(code, details)
        raise self.aborted

    def auth_context(self) -> dict[str, list[bytes]]:
        if not self.peer_certificate:
            return {}
        return {"x509_pem_cert": [self.peer_certificate]}

    def invocation_metadata(self) -> tuple:
        return self.invocation_metadata_value

    def peer(self) -> str:
        return "ipv4:127.0.0.1:0"

    async def set_code(self, code) -> None:
        return None

    async def set_details(self, details: str) -> None:
        return None


@pytest.fixture
def context() -> FakeServicerContext:
    return FakeServicerContext()


def make_service_certificate(
    service_name: str | None,
    *,
    trust_domain: str = identity_module.TRUST_DOMAIN,
    extra_uris: tuple[str, ...] = (),
    include_san: bool = True,
    common_name: str = "test",
) -> bytes:
    key = Ed25519PrivateKey.generate()
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = _datetime.datetime.now(_datetime.UTC)
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - _datetime.timedelta(minutes=5))
        .not_valid_after(now + _datetime.timedelta(days=1))
    )
    if include_san:
        uris: list[str] = []
        if service_name is not None:
            uris.append(f"spiffe://{trust_domain}/service/{service_name}")
        uris.extend(extra_uris)
        builder = builder.add_extension(
            x509.SubjectAlternativeName([x509.UniformResourceIdentifier(value) for value in uris]),
            critical=False,
        )
    certificate = builder.sign(key, None)
    return certificate.public_bytes(Encoding.PEM)


@pytest.fixture
def event_id() -> str:
    return str(uuid.uuid4())
