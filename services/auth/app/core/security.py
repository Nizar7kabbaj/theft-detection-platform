from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import get_settings

_hasher: PasswordHasher | None = None


def _get_hasher() -> PasswordHasher:
    global _hasher
    if _hasher is None:
        settings = get_settings()
        _hasher = PasswordHasher(
            time_cost=settings.argon2_time_cost,
            memory_cost=settings.argon2_memory_cost,
            parallelism=settings.argon2_parallelism,
        )
    return _hasher


def hash_password(password: str) -> str:
    return _get_hasher().hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        _get_hasher().verify(password_hash, password)
        return True
    except (VerifyMismatchError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _get_hasher().check_needs_rehash(password_hash)
