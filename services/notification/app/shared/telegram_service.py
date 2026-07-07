import logging
import re
from functools import lru_cache
from pathlib import Path
import requests
from app.shared.config import settings
from app.shared.metrics import telegram_messages_total
logger = logging.getLogger(__name__)
TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/{method}"
_TELEGRAM_TOKEN_URL = re.compile(r"/bot[^/]+/")


def _sanitized(exc: requests.exceptions.RequestException) -> requests.exceptions.RequestException:
    scrubbed = _TELEGRAM_TOKEN_URL.sub("/bot<redacted>/", str(exc))
    return type(exc)(scrubbed)


@lru_cache(maxsize=1)
def _token() -> str:
    path = settings.TELEGRAM_BOT_TOKEN_FILE
    try:
        token = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        logger.error("telegram token file missing at %s", path)
        return ""
    except OSError as exc:
        logger.error("telegram token file unreadable at %s: %s", path, exc)
        return ""
    if not token:
        logger.error("telegram token file empty at %s", path)
    return token


def is_configured() -> bool:
    return bool(_token()) and bool(settings.TELEGRAM_CHAT_ID)


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
        clean = _sanitized(exc)
        logger.error("telegram send failed: %s", clean)
        telegram_messages_total.add(1, {"method": "message", "result": "failed"})
        raise clean from None
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
        clean = _sanitized(exc)
        logger.error("telegram photo send failed: %s", clean)
        telegram_messages_total.add(1, {"method": "photo", "result": "failed"})
        raise clean from None
    except OSError as exc:
        logger.error("snapshot file read failed: %s", exc)
        telegram_messages_total.add(1, {"method": "photo", "result": "failed"})
        return False
    logger.info("telegram photo sent file=%s", path.name)
    telegram_messages_total.add(1, {"method": "photo", "result": "sent"})
    return True
