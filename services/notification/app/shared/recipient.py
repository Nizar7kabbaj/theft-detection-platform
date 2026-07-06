from __future__ import annotations

from app.shared.config import settings

UNCONFIGURED_RECIPIENT = "unconfigured"


def resolve_recipient() -> str:
    return settings.TELEGRAM_CHAT_ID or UNCONFIGURED_RECIPIENT
