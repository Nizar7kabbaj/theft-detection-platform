from __future__ import annotations

import base64
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.core.pseudonym import PseudonymKeyError, pseudonymize, reset_cache

_DIGEST_BYTES = 32
_SHORT_KEY_BYTES = 16


@pytest.fixture
def key_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def _point_at(content: bytes) -> Path:
        path = tmp_path / "pseudonym_key"
        path.write_bytes(content)
        monkeypatch.setenv("AUTH_PSEUDONYM_KEY_FILE", str(path))
        get_settings.cache_clear()
        reset_cache()
        return path

    yield _point_at
    reset_cache()


def test_pseudonymize_returns_sha256_sized_digest():
    digest = pseudonymize("auth-login-subject", "operator")

    assert isinstance(digest, bytes)
    assert len(digest) == _DIGEST_BYTES


def test_pseudonymize_is_stable_for_same_input():
    first = pseudonymize("auth-login-subject", "operator")
    second = pseudonymize("auth-login-subject", "operator")

    assert first == second


def test_pseudonymize_differs_by_value():
    assert pseudonymize("auth-login-subject", "operator") != pseudonymize(
        "auth-login-subject", "admin"
    )


def test_pseudonymize_differs_by_domain():
    assert pseudonymize("domain-one", "operator") != pseudonymize("domain-two", "operator")


def test_length_prefix_prevents_boundary_collision():
    assert pseudonymize("ab", "c") != pseudonymize("a", "bc")


def test_empty_value_returns_empty_bytes():
    assert pseudonymize("auth-login-subject", "") == b""


def test_empty_domain_is_rejected():
    with pytest.raises(ValueError, match="domain must not be empty"):
        pseudonymize("", "operator")


def test_missing_key_file_raises(key_file, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AUTH_PSEUDONYM_KEY_FILE", str(tmp_path / "absent"))
    get_settings.cache_clear()
    reset_cache()

    with pytest.raises(PseudonymKeyError, match="missing"):
        pseudonymize("auth-login-subject", "operator")


def test_empty_key_file_raises(key_file):
    key_file(b"")

    with pytest.raises(PseudonymKeyError, match="empty"):
        pseudonymize("auth-login-subject", "operator")


def test_non_base64_key_raises(key_file):
    key_file(b"not base64 at all !!")

    with pytest.raises(PseudonymKeyError, match="base64"):
        pseudonymize("auth-login-subject", "operator")


def test_short_key_raises(key_file):
    key_file(base64.b64encode(b"\x01" * _SHORT_KEY_BYTES))

    with pytest.raises(PseudonymKeyError, match="minimum"):
        pseudonymize("auth-login-subject", "operator")


def test_key_is_cached_after_first_read(key_file):
    path = key_file(base64.b64encode(b"\x02" * _DIGEST_BYTES))
    first = pseudonymize("auth-login-subject", "operator")
    path.unlink()

    assert pseudonymize("auth-login-subject", "operator") == first


def test_reset_cache_forces_reread(key_file):
    key_file(base64.b64encode(b"\x03" * _DIGEST_BYTES))
    first = pseudonymize("auth-login-subject", "operator")

    key_file(base64.b64encode(b"\x04" * _DIGEST_BYTES))

    assert pseudonymize("auth-login-subject", "operator") != first
