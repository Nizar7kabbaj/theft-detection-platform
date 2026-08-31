from __future__ import annotations

import base64
import hmac
from hashlib import sha256

import pytest

from app.core import pseudonym
from app.core.config import get_settings
from tests import PSEUDONYM_KEY_FILE, PSEUDONYM_KEY_ID

pytestmark = pytest.mark.unit


def _key() -> bytes:
    return base64.b64decode(PSEUDONYM_KEY_FILE.read_text(encoding="utf-8").strip())


def _expected(domain: str, value: str) -> bytes:
    domain_bytes = domain.encode("utf-8")
    value_bytes = value.encode("utf-8")
    message = (
        len(domain_bytes).to_bytes(8, "big")
        + domain_bytes
        + len(value_bytes).to_bytes(8, "big")
        + value_bytes
    )
    return hmac.new(_key(), message, sha256).digest()


def _point_at(monkeypatch: pytest.MonkeyPatch, path) -> None:
    monkeypatch.setenv("AUDIT_PSEUDONYM_KEY_FILE", str(path))
    get_settings.cache_clear()
    pseudonym.reset_cache()


def test_key_id_comes_from_settings() -> None:
    assert pseudonym.key_id() == PSEUDONYM_KEY_ID


def test_pseudonym_is_thirty_two_bytes() -> None:
    assert len(pseudonym.pseudonymize("actor", "nizar")) == 32


def test_pseudonym_matches_specification() -> None:
    assert pseudonym.pseudonymize("actor", "nizar") == _expected("actor", "nizar")


def test_pseudonym_is_deterministic() -> None:
    first = pseudonym.pseudonymize("actor", "nizar")
    second = pseudonym.pseudonymize("actor", "nizar")
    assert first == second


def test_pseudonym_differs_between_values() -> None:
    assert pseudonym.pseudonymize("actor", "nizar") != pseudonym.pseudonymize("actor", "elwadi")


def test_pseudonym_differs_between_domains() -> None:
    assert pseudonym.pseudonymize("actor", "nizar") != pseudonym.pseudonymize("subject", "nizar")


def test_pseudonym_does_not_reveal_the_value() -> None:
    assert b"nizar" not in pseudonym.pseudonymize("actor", "nizar")


def test_pseudonym_is_not_a_plain_hash_of_the_value() -> None:
    assert pseudonym.pseudonymize("actor", "nizar") != sha256(b"nizar").digest()


def test_empty_value_returns_empty_bytes() -> None:
    assert pseudonym.pseudonymize("actor", "") == b""


def test_empty_domain_is_rejected() -> None:
    with pytest.raises(ValueError, match="domain must not be empty"):
        pseudonym.pseudonymize("", "nizar")


def test_domain_boundary_cannot_be_shifted() -> None:
    assert pseudonym.pseudonymize("ab", "cd") != pseudonym.pseudonymize("abc", "d")


def test_non_ascii_domain_boundary_cannot_be_shifted() -> None:
    assert pseudonym.pseudonymize("é", "ab") != pseudonym.pseudonymize("éa", "b")


def test_non_ascii_domain_matches_specification() -> None:
    assert pseudonym.pseudonymize("actéur", "nizar") == _expected("actéur", "nizar")


def test_non_ascii_value_matches_specification() -> None:
    assert pseudonym.pseudonymize("actor", "nizär") == _expected("actor", "nizär")


def test_matches_accepts_the_true_pseudonym() -> None:
    candidate = pseudonym.pseudonymize("actor", "nizar")
    assert pseudonym.matches("actor", "nizar", candidate) is True


def test_matches_rejects_a_different_value() -> None:
    candidate = pseudonym.pseudonymize("actor", "nizar")
    assert pseudonym.matches("actor", "elwadi", candidate) is False


def test_matches_rejects_a_different_domain() -> None:
    candidate = pseudonym.pseudonymize("actor", "nizar")
    assert pseudonym.matches("subject", "nizar", candidate) is False


def test_matches_rejects_a_truncated_candidate() -> None:
    candidate = pseudonym.pseudonymize("actor", "nizar")[:16]
    assert pseudonym.matches("actor", "nizar", candidate) is False


def test_matches_rejects_empty_candidate() -> None:
    assert pseudonym.matches("actor", "nizar", b"") is False


def test_key_is_loaded_once(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    rotated = tmp_path / "rotated_key"
    rotated.write_bytes(base64.b64encode(b"b" * 32))
    pseudonym.pseudonymize("actor", "nizar")
    monkeypatch.setenv("AUDIT_PSEUDONYM_KEY_FILE", str(rotated))
    get_settings.cache_clear()
    assert pseudonym.pseudonymize("actor", "nizar") == _expected("actor", "nizar")


def test_reset_cache_picks_up_a_rotated_key(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    before = pseudonym.pseudonymize("actor", "nizar")
    rotated = tmp_path / "rotated_key"
    rotated.write_bytes(base64.b64encode(b"b" * 32))
    _point_at(monkeypatch, rotated)
    assert pseudonym.pseudonymize("actor", "nizar") != before


def test_missing_key_file_is_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _point_at(monkeypatch, tmp_path / "absent_key")
    with pytest.raises(pseudonym.PseudonymKeyError, match="missing"):
        pseudonym.pseudonymize("actor", "nizar")


def test_empty_key_file_is_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    empty = tmp_path / "empty_key"
    empty.write_text("   \n", encoding="utf-8")
    _point_at(monkeypatch, empty)
    with pytest.raises(pseudonym.PseudonymKeyError, match="empty"):
        pseudonym.pseudonymize("actor", "nizar")


def test_unreadable_key_file_is_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    directory = tmp_path / "key_directory"
    directory.mkdir()
    _point_at(monkeypatch, directory)
    with pytest.raises(pseudonym.PseudonymKeyError, match="unreadable"):
        pseudonym.pseudonymize("actor", "nizar")


def test_non_base64_key_is_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    broken = tmp_path / "broken_key"
    broken.write_text("not base64 !!!", encoding="utf-8")
    _point_at(monkeypatch, broken)
    with pytest.raises(pseudonym.PseudonymKeyError, match="not valid base64"):
        pseudonym.pseudonymize("actor", "nizar")


@pytest.mark.parametrize("size", [1, 16, 31])
def test_short_key_is_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path, size: int) -> None:
    short = tmp_path / "short_key"
    short.write_bytes(base64.b64encode(b"k" * size))
    _point_at(monkeypatch, short)
    with pytest.raises(pseudonym.PseudonymKeyError, match="minimum 32"):
        pseudonym.pseudonymize("actor", "nizar")


def test_exactly_thirty_two_byte_key_is_accepted(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    exact = tmp_path / "exact_key"
    exact.write_bytes(base64.b64encode(b"k" * 32))
    _point_at(monkeypatch, exact)
    assert len(pseudonym.pseudonymize("actor", "nizar")) == 32


def test_key_file_whitespace_is_stripped(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    padded = tmp_path / "padded_key"
    padded.write_text(f"  {base64.b64encode(b'k' * 32).decode()}  \n", encoding="utf-8")
    _point_at(monkeypatch, padded)
    assert len(pseudonym.pseudonymize("actor", "nizar")) == 32
