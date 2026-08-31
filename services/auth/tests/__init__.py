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

_FIXTURE_DIR = tempfile.TemporaryDirectory(prefix="auth-tests-")
_ROOT = Path(_FIXTURE_DIR.name)

_PSEUDONYM_KEY_BYTES = 32


def _write(name: str, content: bytes) -> Path:
    path = _ROOT / name
    path.write_bytes(content)
    path.chmod(0o600)
    return path


def _write_keypair() -> tuple[Path, Path]:
    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        encoding=Encoding.PEM,
        format=PrivateFormat.PKCS8,
        encryption_algorithm=NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=Encoding.PEM,
        format=PublicFormat.SubjectPublicKeyInfo,
    )
    return _write("jwt_private.pem", private_pem), _write("jwt_public.pem", public_pem)


JWT_PRIVATE_KEY_FILE, JWT_PUBLIC_KEY_FILE = _write_keypair()

PSEUDONYM_KEY_FILE = _write(
    "pseudonym_key",
    base64.b64encode(secrets.token_bytes(_PSEUDONYM_KEY_BYTES)),
)

POSTGRES_APP_PASSWORD_FILE = _write("postgres_app_password", b"harness-app-password")
POSTGRES_OWNER_PASSWORD_FILE = _write("postgres_owner_password", b"harness-owner-password")
REDIS_PASSWORD_FILE = _write("redis_password", b"harness-redis-password")

TLS_CERT_FILE = _ROOT / "tls.crt"
TLS_KEY_FILE = _ROOT / "tls.key"
TLS_CA_FILE = _ROOT / "ca.crt"

os.environ["AUTH_JWT_PRIVATE_KEY_FILE"] = str(JWT_PRIVATE_KEY_FILE)
os.environ["AUTH_JWT_PUBLIC_KEY_FILE"] = str(JWT_PUBLIC_KEY_FILE)
os.environ["AUTH_PSEUDONYM_KEY_FILE"] = str(PSEUDONYM_KEY_FILE)
os.environ["AUTH_POSTGRES_APP_PASSWORD_FILE"] = str(POSTGRES_APP_PASSWORD_FILE)
os.environ["AUTH_POSTGRES_OWNER_PASSWORD_FILE"] = str(POSTGRES_OWNER_PASSWORD_FILE)
os.environ["AUTH_REDIS_PASSWORD_FILE"] = str(REDIS_PASSWORD_FILE)
os.environ["AUTH_TLS_CERT_FILE"] = str(TLS_CERT_FILE)
os.environ["AUTH_TLS_KEY_FILE"] = str(TLS_KEY_FILE)
os.environ["AUTH_TLS_CA_FILE"] = str(TLS_CA_FILE)
os.environ["AUTH_REDIS_TLS"] = "false"
os.environ["AUTH_ARGON2_TIME_COST"] = "1"
os.environ["AUTH_ARGON2_MEMORY_COST"] = "8192"
os.environ["AUTH_ARGON2_PARALLELISM"] = "1"
