import logging
import os
import requests
from ..core.config import settings

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/{method}"
REQUEST_TIMEOUT_SEC = 5
PHOTO_TIMEOUT_SEC   = 15
CAPTION_MAX_CHARS   = 1024


def is_configured() -> bool:
    return bool(settings.TELEGRAM_BOT_TOKEN) and bool(settings.TELEGRAM_CHAT_ID)


def send_message(text: str) -> bool:
    if not is_configured():
        logger.warning("telegram not configured, skipping message")
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
        logger.info("telegram message sent", extra={"chars": len(text)})
        return True
    except requests.exceptions.RequestException as e:
        logger.error("telegram send failed", extra={"error": str(e)})
        return False


def send_photo(image_path: str, caption: str = "") -> bool:
    if not is_configured():
        logger.warning("telegram not configured, skipping photo")
        return False
    if not image_path or not os.path.isfile(image_path):
        logger.warning("snapshot file not found, skipping photo", extra={"path": image_path})
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
        logger.info("telegram photo sent", extra={"file": os.path.basename(image_path)})
        return True
    except requests.exceptions.RequestException as e:
        logger.error("telegram photo send failed", extra={"error": str(e)})
        return False
    except OSError as e:
        logger.error("snapshot file read failed", extra={"error": str(e)})
        return False
