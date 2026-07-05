import logging
from pathlib import Path

import requests

from app.shared.config import settings
from app.shared.metrics import telegram_messages_total

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/{method}"


def is_configured() -> bool:
    return bool(settings.TELEGRAM_BOT_TOKEN) and bool(settings.TELEGRAM_CHAT_ID)


def _token() -> str:
    return settings.TELEGRAM_BOT_TOKEN.get_secret_value()


def send_message(text: str) -> bool:
    if not is_configured():
        logger.warning("telegram not configured, skipping message")
        telegram_messages_total.add(1, {"method": "message", "result": "unconfigured"})
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
    except requests.exceptions.RequestException as exc:
        logger.error("telegram send failed: %s", exc)
        telegram_messages_total.add(1, {"method": "message", "result": "failed"})
        raise
    logger.info("telegram message sent chars=%d", len(text))
    telegram_messages_total.add(1, {"method": "message", "result": "sent"})
    return True


def send_photo(image_path: str, caption: str = "") -> bool:
    if not is_configured():
        logger.warning("telegram not configured, skipping photo")
        telegram_messages_total.add(1, {"method": "photo", "result": "unconfigured"})
        return False
    path = Path(image_path) if image_path else None
    if path is None or not path.is_file():
        logger.warning("snapshot file not found, skipping photo path=%s", image_path)
        telegram_messages_total.add(1, {"method": "photo", "result": "snapshot_missing"})
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
    except requests.exceptions.RequestException as exc:
        logger.error("telegram photo send failed: %s", exc)
        telegram_messages_total.add(1, {"method": "photo", "result": "failed"})
        raise
    except OSError as exc:
        logger.error("snapshot file read failed: %s", exc)
        telegram_messages_total.add(1, {"method": "photo", "result": "failed"})
        return False
    logger.info("telegram photo sent file=%s", path.name)
    telegram_messages_total.add(1, {"method": "photo", "result": "sent"})
    return True
