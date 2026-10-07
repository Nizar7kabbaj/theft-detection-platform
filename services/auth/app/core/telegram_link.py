from __future__ import annotations

import hashlib
import re
import secrets

_TOKEN_BYTES = 32
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}")


def new_link_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def is_well_formed_link_token(token: str) -> bool:
    return _TOKEN_PATTERN.fullmatch(token) is not None


def hash_link_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()
