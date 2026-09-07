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
_HTTP_TOO_MANY_REQUESTS = 429
_HTTP_SERVER_ERROR = 500


class TelegramError(Exception):
    pass


class TelegramUnreachableError(TelegramError):
    pass


class TelegramTransientError(TelegramError):
    pass


class TelegramPermanentError(TelegramError):
    pass


def _scrub(message: str) -> str:
    return _TELEGRAM_TOKEN_URL.sub("/bot<redacted>/", message)


def _classify(exc: requests.exceptions.RequestException) -> TelegramError:
    message = _scrub(str(exc))
    if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
        return TelegramUnreachableError(message)
    if isinstance(exc, requests.exceptions.HTTPError):
        response = exc.response
        status = response.status_code if response is not None else None
        if status is not None and (
            status == _HTTP_TOO_MANY_REQUESTS or status >= _HTTP_SERVER_ERROR
        ):
            return TelegramTransientError(message)
        return TelegramPermanentError(message)
    return TelegramPermanentError(message)


def _result_label(failure: TelegramError) -> str:
    if isinstance(failure, TelegramUnreachableError):
        return "unreachable"
    if isinstance(failure, TelegramTransientError):
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
        response = requests.post(url, json=payload, timeout=settings.TELEGRAM_REQUEST_TIMEOUT_SEC)
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        failure = _classify(exc)
        logger.error("telegram send failed: %s", failure)
        telegram_messages_total.add(1, {"method": "message", "result": _result_label(failure)})
        raise failure from None
    logger.info("telegram message sent chars=%d", len(text))
    telegram_messages_total.add(1, {"method": "message", "result": "sent"})
    return True


def _resolve_media(stored: str) -> Path | None:
    if not stored:
        return None
    root = Path(settings.SNAPSHOTS_DIR).resolve()
    candidate = (root / Path(stored).name).resolve()
    if candidate.parent != root or not candidate.is_file():
        return None
    return candidate


def clip_missing(stored: str) -> bool:
    return _resolve_media(stored) is None


def prefer_annotated(stored: str) -> str:
    if not stored:
        return stored
    name = Path(stored)
    candidate = f"{name.stem}{settings.ANNOTATED_SNAPSHOT_SUFFIX}{name.suffix}"
    if _resolve_media(candidate) is None:
        return stored
    return candidate


def send_photo(image_path: str, caption: str = "") -> bool:
    if not is_configured():
        logger.warning("telegram not configured, skipping photo")
        telegram_messages_total.add(1, {"method": "photo", "result": "unconfigured"})
        return False
    path = _resolve_media(image_path)
    if path is None:
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
        telegram_messages_total.add(1, {"method": "photo", "result": _result_label(failure)})
        raise failure from None
    except OSError as exc:
        logger.error("snapshot file read failed: %s", exc)
        telegram_messages_total.add(1, {"method": "photo", "result": "failed"})
        return False
    logger.info("telegram photo sent file=%s", path.name)
    telegram_messages_total.add(1, {"method": "photo", "result": "sent"})
    return True


def send_media_group(
    image_path: str,
    clip_path: str,
    caption: str = "",
    width: int = 0,
    height: int = 0,
) -> bool:
    if not is_configured():
        logger.warning("telegram not configured, skipping media group")
        telegram_messages_total.add(1, {"method": "media_group", "result": "unconfigured"})
        return False
    photo = _resolve_media(image_path)
    clip = _resolve_media(clip_path)
    if photo is None or clip is None:
        return False
    if len(caption) > settings.TELEGRAM_CAPTION_MAX_CHARS:
        caption = caption[: settings.TELEGRAM_CAPTION_MAX_CHARS - 3] + "..."
    url = TELEGRAM_API_URL.format(token=_token(), method="sendPhoto")
    try:
        with photo.open("rb") as img:
            response = requests.post(
                url,
                data={
                    "chat_id": settings.TELEGRAM_CHAT_ID,
                    "caption": caption,
                    "parse_mode": "HTML",
                },
                files={"photo": (photo.name, img, "image/jpeg")},
                timeout=settings.TELEGRAM_PHOTO_TIMEOUT_SEC,
            )
        response.raise_for_status()
        url = TELEGRAM_API_URL.format(token=_token(), method="sendVideo")
        data = {"chat_id": settings.TELEGRAM_CHAT_ID, "supports_streaming": True}
        if width and height:
            data["width"] = width
            data["height"] = height
        with clip.open("rb") as vid:
            response = requests.post(
                url,
                data=data,
                files={"video": (clip.name, vid, "video/mp4")},
                timeout=settings.TELEGRAM_CLIP_TIMEOUT_SEC,
            )
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        failure = _classify(exc)
        logger.error("telegram media group send failed: %s", failure)
        telegram_messages_total.add(1, {"method": "media_group", "result": _result_label(failure)})
        raise failure from None
    except OSError as exc:
        logger.error("media file read failed: %s", exc)
        telegram_messages_total.add(1, {"method": "media_group", "result": "failed"})
        return False
    logger.info("telegram media group sent file=%s clip=%s", photo.name, clip.name)
    telegram_messages_total.add(1, {"method": "media_group", "result": "sent"})
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
