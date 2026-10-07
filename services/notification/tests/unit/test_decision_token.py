from __future__ import annotations

import base64
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.shared import decision_token
from app.shared.decision_token import (
    ButtonDecision,
    DecisionTokenError,
    decision_keyboard,
    sign,
    verify,
)

pytestmark = pytest.mark.unit

INTENT = "65f0c0ffee0000000000abcd"
NOW = 1_800_000_000
_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"


def _write_key(path: Path, hex_text: str) -> None:
    path.write_text(hex_text + "\n", encoding="ascii")
    decision_token._key.cache_clear()


@pytest.fixture(autouse=True)
def key_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    path = tmp_path / "callback_key"
    monkeypatch.setattr(decision_token.settings, "TELEGRAM_CALLBACK_KEY_FILE", path)
    _write_key(path, "11" * 32)
    yield path
    decision_token._key.cache_clear()


def _raw(token: str) -> bytearray:
    return bytearray(base64.urlsafe_b64decode(token + "=="))


def _encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(bytes(raw)).decode("ascii").rstrip("=")


def _reason(token: str, now: float = NOW) -> str:
    with pytest.raises(DecisionTokenError) as caught:
        verify(token, now=now)
    return caught.value.reason


def test_round_trip_keeps_intent_and_decision() -> None:
    claim = verify(sign(INTENT, ButtonDecision.DISMISSED, now=NOW), now=NOW)
    assert claim.intent_id == INTENT
    assert claim.decision is ButtonDecision.DISMISSED
    assert claim.expires_at == NOW + decision_token.settings.TELEGRAM_BUTTON_TTL_SEC


def test_token_fits_the_telegram_callback_limit() -> None:
    token = sign(INTENT, ButtonDecision.CONFIRMED, now=NOW)
    assert len(token) == 46
    assert len(token.encode("ascii")) <= 64


def test_changed_decision_byte_breaks_the_signature() -> None:
    raw = _raw(sign(INTENT, ButtonDecision.DISMISSED, now=NOW))
    raw[1] = ButtonDecision.CONFIRMED.value
    assert _reason(_encode(raw)) == "bad_signature"


def test_changed_intent_breaks_the_signature() -> None:
    raw = _raw(sign(INTENT, ButtonDecision.CONFIRMED, now=NOW))
    raw[10] ^= 0x01
    assert _reason(_encode(raw)) == "bad_signature"


def test_key_change_invalidates_old_buttons(key_file: Path) -> None:
    token = sign(INTENT, ButtonDecision.CONFIRMED, now=NOW)
    _write_key(key_file, "22" * 32)
    assert _reason(token) == "bad_signature"


def test_expired_button_is_refused() -> None:
    token = sign(INTENT, ButtonDecision.UNSURE, now=NOW)
    later = NOW + decision_token.settings.TELEGRAM_BUTTON_TTL_SEC + 1
    assert _reason(token, now=later) == "expired"


def test_unknown_version_is_refused() -> None:
    raw = _raw(sign(INTENT, ButtonDecision.CONFIRMED, now=NOW))
    raw[0] = 2
    assert _reason(_encode(raw)) == "unknown_version"


@pytest.mark.parametrize("token", ["", "short", "!" * 46, "A" * 47])
def test_malformed_tokens_are_refused(token: str) -> None:
    assert _reason(token) == "malformed"


def test_non_canonical_spelling_is_refused() -> None:
    token = sign(INTENT, ButtonDecision.CONFIRMED, now=NOW)
    last = _ALPHABET.index(token[-1])
    twin = token[:-1] + _ALPHABET[last ^ 0x01]
    assert _reason(twin) == "malformed"


def test_short_key_is_rejected(key_file: Path) -> None:
    _write_key(key_file, "11" * 16)
    with pytest.raises(RuntimeError, match="32 bytes"):
        sign(INTENT, ButtonDecision.CONFIRMED, now=NOW)


def test_sign_rejects_a_non_object_id() -> None:
    with pytest.raises(ValueError, match="object id"):
        sign("cam-a-1-28409-3", ButtonDecision.CONFIRMED, now=NOW)


def test_keyboard_has_confirmed_alone_then_dismissed_and_unsure() -> None:
    keyboard = decision_keyboard(INTENT, now=NOW)
    rows = keyboard["inline_keyboard"]
    assert [[button["text"] for button in row] for row in rows] == [
        ["confirmed"],
        ["dismissed", "unsure"],
    ]
    decisions = [
        verify(button["callback_data"], now=NOW).decision for row in rows for button in row
    ]
    assert decisions == [ButtonDecision.CONFIRMED, ButtonDecision.DISMISSED, ButtonDecision.UNSURE]
