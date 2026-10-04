from __future__ import annotations

import secrets
import time
import uuid

_VERSION = 7
_VARIANT = 0b10
_MILLIS_MASK = (1 << 48) - 1


def new_alert_id() -> str:
    millis = time.time_ns() // 1_000_000
    value = (millis & _MILLIS_MASK) << 80
    value |= _VERSION << 76
    value |= secrets.randbits(12) << 64
    value |= _VARIANT << 62
    value |= secrets.randbits(62)
    return str(uuid.UUID(int=value))
