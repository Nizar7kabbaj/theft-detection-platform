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


class TelegramError(Exception):
    pass


class TelegramUnreachable(TelegramError):
    pass


class TelegramTransient(TelegramError):
    pass


class TelegramPermanent(TelegramError):
    pass


def _scrub(message: str) -> str:
    return _TELEGRAM_TOKEN_URL.sub("/bot<redacted>/", message)


def _classify(exc: requests.exceptions.RequestException) -> TelegramError:
    message = _scrub(str(exc))
    if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
        return TelegramUnreachable(message)
    if isinstance(exc, requests.exceptions.HTTPError):
        response = exc.response
        status = response.status_code if response is not None else None
        if status is not None and (status == 429 or status >= 500):
            return TelegramTransient(message)
        return TelegramPermanent(message)
    return TelegramPermanent(message)


def _result_label(failure: TelegramError) -> str:
    if isinstance(failure, TelegramUnreachable):
        return "unreachable"
    if isinstance(failure, TelegramTransient):
        return "transient"
    return "permanent"


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
        failure = _classify(exc)
        logger.error("telegram send failed: %s", failure)
        telegram_messages_total.add(
            1, {"method": "message", "result": _result_label(failure)}
        )
        raise failure from None
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
        failure = _classify(exc)
        logger.error("telegram photo send failed: %s", failure)
        telegram_messages_total.add(
            1, {"method": "photo", "result": _result_label(failure)}
        )
        raise failure from None
    except OSError as exc:
        logger.error("snapshot file read failed: %s", exc)
        telegram_messages_total.add(1, {"method": "photo", "result": "failed"})
        return False
    logger.info("telegram photo sent file=%s", path.name)
    telegram_messages_total.add(1, {"method": "photo", "result": "sent"})
    return True

def probe() -> bool:
    if not is_configured():
        return False
    url = TELEGRAM_API_URL.format(token=_token(), method="getMe")
    try:
        response = requests.get(url, timeout=settings.TELEGRAM_REQUEST_TIMEOUT_SEC)
        response.raise_for_status()
    except requests.exceptions.RequestException:
        return False
    return True
