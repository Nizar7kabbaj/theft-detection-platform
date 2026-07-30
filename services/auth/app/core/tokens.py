from __future__ import annotations
import enum
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
import jwt
from app.core.config import get_settings
from app.core.keys import load_private_key, load_public_key
_ALGORITHM = "EdDSA"


class TokenFailure(enum.Enum):
    EXPIRED = "expired"
    AUDIENCE_MISMATCH = "audience_mismatch"
    SIGNATURE_INVALID = "signature_invalid"
    MALFORMED = "malformed"


class TokenError(Exception):
    def __init__(self, message: str, failure: TokenFailure = TokenFailure.MALFORMED) -> None:
        super().__init__(message)
        self.failure = failure


def new_jti() -> str:
    return str(uuid.uuid4())


def new_refresh_secret() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def sign_access_token(user_id: str, username: str, roles: list[str], session_id: str) -> tuple[str, str, datetime]:
    settings = get_settings()
    jti = new_jti()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=settings.access_token_ttl_seconds)
    claims = {
        "sub": user_id,
        "username": username,
        "roles": roles,
        "sid": session_id,
        "jti": jti,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(claims, load_private_key(), algorithm=_ALGORITHM)
    return token, jti, expires_at


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(
            token,
            load_public_key(),
            algorithms=[_ALGORITHM],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={
                "require": ["exp", "nbf", "iat", "iss", "aud", "sub", "jti"],
                "verify_signature": True,
                "verify_exp": True,
                "verify_nbf": True,
                "verify_iss": True,
                "verify_aud": True,
            },
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError(str(exc), TokenFailure.EXPIRED) from exc
    except jwt.InvalidAudienceError as exc:
        raise TokenError(str(exc), TokenFailure.AUDIENCE_MISMATCH) from exc
    except jwt.InvalidSignatureError as exc:
        raise TokenError(str(exc), TokenFailure.SIGNATURE_INVALID) from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError(str(exc), TokenFailure.MALFORMED) from exc
