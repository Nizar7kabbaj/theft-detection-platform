from __future__ import annotations

import uuid
from datetime import UTC, datetime

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)

from app.core.config import get_settings
from app.core.keys import load_private_key
from app.core.tokens import (
    TokenError,
    TokenFailure,
    decode_access_token,
    hash_refresh_secret,
    new_jti,
    new_refresh_secret,
    sign_access_token,
)

_ALGORITHM = "EdDSA"
_SHA256_HEX_LENGTH = 64


def _claims(**overrides: object) -> dict[str, object]:
    settings = get_settings()
    now = int(datetime.now(UTC).timestamp())
    base: dict[str, object] = {
        "sub": "11111111-1111-1111-1111-111111111111",
        "username": "operator",
        "roles": ["operator"],
        "sid": "22222222-2222-2222-2222-222222222222",
        "jti": str(uuid.uuid4()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "nbf": now,
        "exp": now + 600,
    }
    base.update(overrides)
    return base


def _foreign_private_pem() -> str:
    key = Ed25519PrivateKey.generate()
    return key.private_bytes(
        encoding=Encoding.PEM,
        format=PrivateFormat.PKCS8,
        encryption_algorithm=NoEncryption(),
    ).decode("utf-8")


def test_sign_access_token_round_trips():
    token, jti, expires_at = sign_access_token(
        user_id="11111111-1111-1111-1111-111111111111",
        username="operator",
        roles=["operator", "viewer"],
        session_id="22222222-2222-2222-2222-222222222222",
    )
    claims = decode_access_token(token)

    assert claims["sub"] == "11111111-1111-1111-1111-111111111111"
    assert claims["username"] == "operator"
    assert claims["roles"] == ["operator", "viewer"]
    assert claims["sid"] == "22222222-2222-2222-2222-222222222222"
    assert claims["jti"] == jti
    assert claims["exp"] == int(expires_at.timestamp())


def test_signed_token_expiry_matches_configured_ttl():
    settings = get_settings()
    _, _, expires_at = sign_access_token(
        user_id="user", username="operator", roles=[], session_id="session"
    )
    delta = (expires_at - datetime.now(UTC)).total_seconds()

    assert expires_at.tzinfo is not None
    assert abs(delta - settings.access_token_ttl_seconds) < 5


def test_expired_token_reports_expired():
    token = jwt.encode(
        _claims(exp=int(datetime.now(UTC).timestamp()) - 10),
        load_private_key(),
        algorithm=_ALGORITHM,
    )
    with pytest.raises(TokenError) as excinfo:
        decode_access_token(token)

    assert excinfo.value.failure is TokenFailure.EXPIRED


def test_wrong_audience_reports_audience_mismatch():
    token = jwt.encode(
        _claims(aud="some-other-platform"),
        load_private_key(),
        algorithm=_ALGORITHM,
    )
    with pytest.raises(TokenError) as excinfo:
        decode_access_token(token)

    assert excinfo.value.failure is TokenFailure.AUDIENCE_MISMATCH


def test_foreign_signature_reports_signature_invalid():
    token = jwt.encode(_claims(), _foreign_private_pem(), algorithm=_ALGORITHM)
    with pytest.raises(TokenError) as excinfo:
        decode_access_token(token)

    assert excinfo.value.failure is TokenFailure.SIGNATURE_INVALID


def test_garbage_token_reports_malformed():
    with pytest.raises(TokenError) as excinfo:
        decode_access_token("not-a-jwt")

    assert excinfo.value.failure is TokenFailure.MALFORMED


def test_missing_required_claim_reports_malformed():
    claims = _claims()
    del claims["jti"]
    token = jwt.encode(claims, load_private_key(), algorithm=_ALGORITHM)
    with pytest.raises(TokenError) as excinfo:
        decode_access_token(token)

    assert excinfo.value.failure is TokenFailure.MALFORMED


def test_wrong_issuer_is_rejected():
    token = jwt.encode(
        _claims(iss="someone-else"),
        load_private_key(),
        algorithm=_ALGORITHM,
    )
    with pytest.raises(TokenError):
        decode_access_token(token)


def test_new_jti_is_a_unique_uuid():
    first = new_jti()
    second = new_jti()

    assert uuid.UUID(first)
    assert first != second


def test_refresh_secret_is_unique_and_long():
    first = new_refresh_secret()
    second = new_refresh_secret()

    assert first != second
    assert len(first) >= 40


def test_hash_refresh_secret_is_stable_sha256_hex():
    secret = "abc123"
    digest = hash_refresh_secret(secret)

    assert digest == hash_refresh_secret(secret)
    assert len(digest) == _SHA256_HEX_LENGTH
    assert digest != hash_refresh_secret("abc124")
