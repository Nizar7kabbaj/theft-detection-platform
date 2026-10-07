from __future__ import annotations

import base64
import binascii
import hmac
import struct
import time
from dataclasses import dataclass
from enum import IntEnum
from functools import lru_cache
from hashlib import sha256
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId

from app.shared.config import settings

_VERSION = 1
_CONTEXT = b"theft-detection-platform/telegram-decision"
_LAYOUT = struct.Struct(">BBI12s")
_TAG_BYTES = 16
_RAW_BYTES = _LAYOUT.size + _TAG_BYTES
_TOKEN_CHARS = 46
_KEY_BYTES = 32


class ButtonDecision(IntEnum):
    CONFIRMED = 1
    DISMISSED = 2
    UNSURE = 3

    @property
    def wire(self) -> str:
        return f"DECISION_{self.name}"

    @property
    def label(self) -> str:
        return self.name.lower()


class DecisionTokenError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class ButtonClaim:
    intent_id: str
    decision: ButtonDecision
    expires_at: int


@lru_cache(maxsize=1)
def _key() -> bytes:
    text = settings.TELEGRAM_CALLBACK_KEY_FILE.read_text(encoding="ascii").strip()
    try:
        key = bytes.fromhex(text)
    except ValueError:
        raise RuntimeError("telegram callback key is not hex") from None
    if len(key) != _KEY_BYTES:
        raise RuntimeError("telegram callback key must be 32 bytes")
    return key


def _tag(body: bytes) -> bytes:
    return hmac.new(_key(), _CONTEXT + body, sha256).digest()[:_TAG_BYTES]


def _encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _now(now: float | None) -> int:
    return int(time.time() if now is None else now)


def sign(intent_id: str, decision: ButtonDecision, now: float | None = None) -> str:
    try:
        oid = ObjectId(intent_id)
    except (InvalidId, TypeError):
        raise ValueError("intent id is not an object id") from None
    expires_at = _now(now) + settings.TELEGRAM_BUTTON_TTL_SEC
    body = _LAYOUT.pack(_VERSION, decision.value, expires_at, oid.binary)
    return _encode(body + _tag(body))


def verify(token: str, now: float | None = None) -> ButtonClaim:
    if len(token) != _TOKEN_CHARS:
        raise DecisionTokenError("malformed")
    try:
        raw = base64.b64decode(token + "==", altchars=b"-_", validate=True)
    except (binascii.Error, ValueError):
        raise DecisionTokenError("malformed") from None
    if len(raw) != _RAW_BYTES or _encode(raw) != token:
        raise DecisionTokenError("malformed")
    body, tag = raw[: _LAYOUT.size], raw[_LAYOUT.size :]
    version, code, expires_at, oid = _LAYOUT.unpack(body)
    if version != _VERSION:
        raise DecisionTokenError("unknown_version")
    if not hmac.compare_digest(tag, _tag(body)):
        raise DecisionTokenError("bad_signature")
    try:
        decision = ButtonDecision(code)
    except ValueError:
        raise DecisionTokenError("malformed") from None
    if _now(now) > expires_at:
        raise DecisionTokenError("expired")
    return ButtonClaim(intent_id=str(ObjectId(oid)), decision=decision, expires_at=expires_at)


def decision_keyboard(intent_id: str, now: float | None = None) -> dict[str, Any]:
    issued = _now(now)

    def button(decision: ButtonDecision) -> dict[str, str]:
        return {"text": decision.label, "callback_data": sign(intent_id, decision, issued)}

    return {
        "inline_keyboard": [
            [button(ButtonDecision.CONFIRMED)],
            [button(ButtonDecision.DISMISSED), button(ButtonDecision.UNSURE)],
        ]
    }
