from __future__ import annotations

import base64
import os
import secrets
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

_MATERIAL = tempfile.TemporaryDirectory(prefix="audit-tests-")

MATERIAL_DIR = Path(_MATERIAL.name)

CHECKPOINT_KEY_ID = "c1"
PSEUDONYM_KEY_ID = "p1"


def write_material(name: str, data: bytes) -> Path:
    path = MATERIAL_DIR / name
    path.write_bytes(data)
    path.chmod(0o600)
    return path


def ed25519_pem_pair() -> tuple[bytes, bytes]:
    private = Ed25519PrivateKey.generate()
    private_pem = private.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    public_pem = private.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    return private_pem, public_pem


_CHECKPOINT_PRIVATE_PEM, _CHECKPOINT_PUBLIC_PEM = ed25519_pem_pair()

CHECKPOINT_PRIVATE_KEY_FILE = write_material("checkpoint_private.pem", _CHECKPOINT_PRIVATE_PEM)
CHECKPOINT_PUBLIC_KEY_FILE = write_material("checkpoint_public.pem", _CHECKPOINT_PUBLIC_PEM)
PSEUDONYM_KEY_FILE = write_material(
    "pseudonym_key", base64.b64encode(secrets.token_bytes(32)) + b"\n"
)
POSTGRES_APP_PASSWORD_FILE = write_material("postgres_app_password", b"audit-app-test\n")
POSTGRES_OWNER_PASSWORD_FILE = write_material("postgres_owner_password", b"audit-owner-test\n")
REDIS_PASSWORD_FILE = write_material("redis_password", b"audit-redis-test\n")

_PINNED_ENVIRONMENT = {
    "AUDIT_SERVICE_NAME": "audit",
    "AUDIT_GRPC_HOST": "127.0.0.1",
    "AUDIT_GRPC_PORT": "50054",
    "AUDIT_GRPC_MAX_WORKERS": "4",
    "AUDIT_GRPC_MAX_CONCURRENT_RPCS": "16",
    "AUDIT_LOG_LEVEL": "warning",
    "AUDIT_POSTGRES_HOST": "127.0.0.1",
    "AUDIT_POSTGRES_PORT": "5432",
    "AUDIT_POSTGRES_DB": "auditdb",
    "AUDIT_POSTGRES_APP_USER": "audit_app",
    "AUDIT_POSTGRES_APP_PASSWORD_FILE": str(POSTGRES_APP_PASSWORD_FILE),
    "AUDIT_POSTGRES_OWNER_USER": "audit_owner",
    "AUDIT_POSTGRES_OWNER_PASSWORD_FILE": str(POSTGRES_OWNER_PASSWORD_FILE),
    "AUDIT_REDIS_HOST": "127.0.0.1",
    "AUDIT_REDIS_PORT": "6380",
    "AUDIT_REDIS_TLS": "false",
    "AUDIT_REDIS_USER": "audit",
    "AUDIT_REDIS_DB": "0",
    "AUDIT_REDIS_PASSWORD_FILE": str(REDIS_PASSWORD_FILE),
    "AUDIT_TLS_ENABLED": "false",
    "AUDIT_TLS_REQUIRE_CLIENT_AUTH": "false",
    "AUDIT_APPEND_RATE_LIMIT": "2000",
    "AUDIT_APPEND_RATE_WINDOW_SECONDS": "1",
    "AUDIT_APPEND_RATE_FAIL_CLOSED": "false",
    "AUDIT_SCHEMA_VERSION": "1",
    "AUDIT_MIN_ACCEPTED_SCHEMA_VERSION": "1",
    "AUDIT_MAX_CLOCK_SKEW_SECONDS": "300",
    "AUDIT_MAX_BACKDATE_SECONDS": "604800",
    "AUDIT_PSEUDONYM_KEY_FILE": str(PSEUDONYM_KEY_FILE),
    "AUDIT_PSEUDONYM_KEY_ID": PSEUDONYM_KEY_ID,
    "AUDIT_CHECKPOINT_PRIVATE_KEY_FILE": str(CHECKPOINT_PRIVATE_KEY_FILE),
    "AUDIT_CHECKPOINT_PUBLIC_KEY_FILE": str(CHECKPOINT_PUBLIC_KEY_FILE),
    "AUDIT_CHECKPOINT_KEY_ID": CHECKPOINT_KEY_ID,
    "AUDIT_CHECKPOINT_INTERVAL_EVENTS": "1000",
    "AUDIT_CHECKPOINT_INTERVAL_SECONDS": "1",
    "AUDIT_RETENTION_DAYS": "365",
    "AUDIT_SEGMENT_INTERVAL_DAYS": "30",
    "AUDIT_RETENTION_MAX_ROWS_PER_RUN": "50000",
}

for _name, _value in _PINNED_ENVIRONMENT.items():
    os.environ[_name] = _value
