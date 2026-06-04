import os
import requests
from loguru import logger
from ..core.config import settings


TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/{method}"
REQUEST_TIMEOUT_SEC = 5
PHOTO_TIMEOUT_SEC   = 15
CAPTION_MAX_CHARS   = 1024


def is_configured() -> bool:
    return bool(settings.TELEGRAM_BOT_TOKEN) and bool(settings.TELEGRAM_CHAT_ID)


def send_message(text: str) -> bool:
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
    if not is_configured():
        logger.warning("Telegram not configured — skipping photo")
        return False

    if not image_path or not os.path.isfile(image_path):
        logger.warning(f"Snapshot file not found, skipping photo: {image_path}")
        return False

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
