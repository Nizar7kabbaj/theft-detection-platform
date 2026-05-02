"""
telegram_service.py — TDP-35 + TDP-36
Sends notifications to a Telegram chat (group or private) via the Bot API.
Designed to fail silently: if the bot is not configured or the network is
down, it logs a warning but never crashes the caller.

TDP-35: send_message (text only)
TDP-36: send_photo  (JPEG snapshot + caption)
"""
import os
import requests
from loguru import logger
from backend.app.core.config import settings


TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/{method}"
REQUEST_TIMEOUT_SEC = 5          # text messages are tiny
PHOTO_TIMEOUT_SEC   = 15         # uploads need a bit more headroom
CAPTION_MAX_CHARS   = 1024       # Telegram hard limit for sendPhoto captions


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


def send_photo(image_path: str, caption: str = "") -> bool:
    """
    Send a photo (JPEG/PNG) with an optional caption to the Telegram chat.
    Returns True on success, False on any failure (never raises).

    The caption is automatically truncated to Telegram's 1024-char limit.
    If the image file does not exist, returns False without sending anything.
    """
    if not is_configured():
        logger.warning("Telegram not configured — skipping photo")
        return False

    if not image_path or not os.path.isfile(image_path):
        logger.warning(f"Snapshot file not found, skipping photo: {image_path}")
        return False

    # Telegram caption limit — truncate defensively
    if len(caption) > CAPTION_MAX_CHARS:
        caption = caption[: CAPTION_MAX_CHARS - 3] + "..."

    url = TELEGRAM_API_URL.format(
        token=settings.TELEGRAM_BOT_TOKEN,
        method="sendPhoto",
    )
    data = {
        "chat_id": settings.TELEGRAM_CHAT_ID,
        "caption": caption,
        "parse_mode": "HTML",
    }

    try:
        with open(image_path, "rb") as img:
            files = {"photo": (os.path.basename(image_path), img, "image/jpeg")}
            response = requests.post(url, data=data, files=files, timeout=PHOTO_TIMEOUT_SEC)
        response.raise_for_status()
        logger.success(f"Telegram photo sent: {os.path.basename(image_path)}")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Telegram photo send failed: {e}")
        return False
    except OSError as e:
        logger.error(f"Could not read snapshot file: {e}")
        return False