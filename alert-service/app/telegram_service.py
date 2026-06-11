import logging
from pathlib import Path

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/{method}"


def is_configured() -> bool:
    return bool(settings.TELEGRAM_BOT_TOKEN) and bool(settings.TELEGRAM_CHAT_ID)


def _token() -> str:
    return settings.TELEGRAM_BOT_TOKEN.get_secret_value()


def send_message(text: str) -> bool:
    if not is_configured():
        logger.warning("telegram not configured, skipping message")
        return False
    url = TELEGRAM_API_URL.format(token=_token(), method="sendMessage")
    payload = {
        "chat_id": settings.TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
    }
    try:
        response = requests.post(
            url, json=payload, timeout=settings.TELEGRAM_REQUEST_TIMEOUT_SEC
        )
        response.raise_for_status()
        logger.info("telegram message sent chars=%d", len(text))
        return True
    except requests.exceptions.RequestException as exc:
        logger.error("telegram send failed: %s", exc)
        return False


def send_photo(image_path: str, caption: str = "") -> bool:
    if not is_configured():
        logger.warning("telegram not configured, skipping photo")
        return False
    path = Path(image_path) if image_path else None
    if path is None or not path.is_file():
        logger.warning("snapshot file not found, skipping photo path=%s", image_path)
        return False
    if len(caption) > settings.TELEGRAM_CAPTION_MAX_CHARS:
        caption = caption[: settings.TELEGRAM_CAPTION_MAX_CHARS - 3] + "..."
    url = TELEGRAM_API_URL.format(token=_token(), method="sendPhoto")
    data = {
        "chat_id": settings.TELEGRAM_CHAT_ID,
        "caption": caption,
        "parse_mode": "HTML",
    }
    try:
        with path.open("rb") as img:
            files = {"photo": (path.name, img, "image/jpeg")}
            response = requests.post(
                url, data=data, files=files, timeout=settings.TELEGRAM_PHOTO_TIMEOUT_SEC
            )
        response.raise_for_status()
        logger.info("telegram photo sent file=%s", path.name)
        return True
    except requests.exceptions.RequestException as exc:
        logger.error("telegram photo send failed: %s", exc)
        return False
    except OSError as exc:
        logger.error("snapshot file read failed: %s", exc)
        return False
