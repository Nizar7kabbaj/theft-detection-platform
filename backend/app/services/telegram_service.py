"""
telegram_service.py — TDP-35
Sends notifications to a Telegram chat (group or private) via the Bot API.
Designed to fail silently: if the bot is not configured or the network is
down, it logs a warning but never crashes the caller.
"""
import requests
from loguru import logger
from backend.app.core.config import settings


TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/{method}"
REQUEST_TIMEOUT_SEC = 5


def is_configured() -> bool:
    """Return True only if both token and chat_id are set in .env."""
    return bool(settings.TELEGRAM_BOT_TOKEN) and bool(settings.TELEGRAM_CHAT_ID)


def send_message(text: str) -> bool:
    """
    Send a plain text message to the configured Telegram chat.
    Returns True on success, False on any failure (never raises).
    """
    if not is_configured():
        logger.warning("Telegram not configured (missing token or chat_id) — skipping message")
        return False

    url = TELEGRAM_API_URL.format(
        token=settings.TELEGRAM_BOT_TOKEN,
        method="sendMessage",
    )
    payload = {
        "chat_id": settings.TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
    }

    try:
        response = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT_SEC)
        response.raise_for_status()
        logger.success(f"Telegram message sent ({len(text)} chars)")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Telegram send failed: {e}")
        return False