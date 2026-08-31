from __future__ import annotations

import pytest
from argon2 import PasswordHasher

from app.core import security
from app.core.config import get_settings
from app.core.security import hash_password, needs_rehash, verify_password

_LIVE_MEMORY_COST = 65536
_LIVE_TIME_COST = 3


def test_hash_password_produces_argon2id_hash():
    digest = hash_password("correct-horse")

    assert digest.startswith("$argon2id$")
    assert "correct-horse" not in digest


def test_hash_password_salts_each_call():
    assert hash_password("same-password") != hash_password("same-password")


def test_verify_password_accepts_matching_password():
    digest = hash_password("correct-horse")

    assert verify_password(digest, "correct-horse") is True


def test_verify_password_rejects_wrong_password():
    digest = hash_password("correct-horse")

    assert verify_password(digest, "battery-staple") is False


def test_verify_password_rejects_malformed_hash():
    assert verify_password("not-a-hash", "correct-horse") is False


def test_verify_password_rejects_empty_hash():
    assert verify_password("", "correct-horse") is False


def test_needs_rehash_is_false_for_current_parameters():
    digest = hash_password("correct-horse")

    assert needs_rehash(digest) is False


def test_needs_rehash_is_true_for_weaker_parameters():
    weak = PasswordHasher(time_cost=1, memory_cost=1024, parallelism=1)
    digest = weak.hash("correct-horse")

    assert needs_rehash(digest) is True


def test_hasher_reads_parameters_from_settings():
    settings = get_settings()
    hasher = security._get_hasher()

    assert hasher.time_cost == settings.argon2_time_cost
    assert hasher.memory_cost == settings.argon2_memory_cost
    assert hasher.parallelism == settings.argon2_parallelism


def test_hasher_honours_deployed_cost_parameters(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AUTH_ARGON2_TIME_COST", str(_LIVE_TIME_COST))
    monkeypatch.setenv("AUTH_ARGON2_MEMORY_COST", str(_LIVE_MEMORY_COST))
    get_settings.cache_clear()
    security._hasher = None

    hasher = security._get_hasher()

    assert hasher.time_cost == _LIVE_TIME_COST
    assert hasher.memory_cost == _LIVE_MEMORY_COST


def test_hasher_is_reused_across_calls():
    first = security._get_hasher()
    second = security._get_hasher()

    assert first is second
