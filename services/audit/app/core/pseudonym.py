from __future__ import annotations

import base64
import binascii
import hmac
import logging
from functools import lru_cache
from hashlib import sha256

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_MIN_KEY_BYTES = 32


class PseudonymKeyError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _load_key() -> bytes:
    path = get_settings().pseudonym_key_file
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise PseudonymKeyError(f"pseudonym key file missing at {path}") from exc
    except OSError as exc:
        raise PseudonymKeyError(f"pseudonym key file unreadable at {path}") from exc
    if not raw:
        raise PseudonymKeyError(f"pseudonym key file empty at {path}")
    try:
        key = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise PseudonymKeyError(f"pseudonym key at {path} is not valid base64") from exc
    if len(key) < _MIN_KEY_BYTES:
        raise PseudonymKeyError(
            f"pseudonym key at {path} is {len(key)} bytes, minimum {_MIN_KEY_BYTES}"
        )
    return key


def key_id() -> str:
    return get_settings().pseudonym_key_id


def pseudonymize(domain: str, value: str) -> bytes:
    if not domain:
        raise ValueError("domain must not be empty")
    if not value:
        return b""
    key = _load_key()
    domain_bytes = domain.encode("utf-8")
    value_bytes = value.encode("utf-8")
    message = b"".join(
        [
            len(domain_bytes).to_bytes(8, "big"),
            domain_bytes,
            len(value_bytes).to_bytes(8, "big"),
            value_bytes,
        ]
    )
    return hmac.new(key, message, sha256).digest()


def matches(domain: str, value: str, candidate: bytes) -> bool:
    return hmac.compare_digest(pseudonymize(domain, value), candidate)


def reset_cache() -> None:
    _load_key.cache_clear()
