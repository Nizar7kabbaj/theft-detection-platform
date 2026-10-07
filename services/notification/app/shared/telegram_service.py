from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx

from app.shared.config import settings
from app.shared.metrics import telegram_messages_total

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/"
_TELEGRAM_TOKEN_URL = re.compile(r"/bot[^/]+/")
_HTTP_TOO_MANY_REQUESTS = 429
_HTTP_SERVER_ERROR = 500
_NOT_MODIFIED = "message is not modified"
_POLL_GRACE_SEC = 10
_ALLOWED_UPDATES = ["callback_query", "message"]
_REMOVE_KEYBOARD: dict[str, Any] = {"inline_keyboard": []}


class TelegramError(Exception):
    pass


class TelegramUnreachableError(TelegramError):
    pass


class TelegramTransientError(TelegramError):
    def __init__(self, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class TelegramPermanentError(TelegramError):
    def __init__(self, message: str, description: str = "") -> None:
        super().__init__(message)
        self.description = description


class MessageKind(StrEnum):
    VIDEO = "video"
    PHOTO = "photo"
    TEXT = "text"


@dataclass(frozen=True, slots=True)
class SentMessage:
    chat_id: int
    message_id: int
    kind: MessageKind


def _scrub(message: str) -> str:
    return _TELEGRAM_TOKEN_URL.sub("/bot<redacted>/", message)


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


def open_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=TELEGRAM_API_BASE.format(token=_token()),
        timeout=httpx.Timeout(settings.TELEGRAM_REQUEST_TIMEOUT_SEC),
        follow_redirects=False,
    )


async def _call(
    client: httpx.AsyncClient,
    method: str,
    *,
    timeout: float,
    json_body: dict[str, Any] | None = None,
    data: dict[str, str] | None = None,
    files: dict[str, tuple[str, bytes, str]] | None = None,
) -> Any:
    try:
        response = await client.post(
            method, json=json_body, data=data, files=files, timeout=timeout
        )
    except httpx.TransportError as exc:
        raise TelegramUnreachableError(_scrub(f"{method}: {type(exc).__name__}")) from None
    try:
        body = response.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    status = response.status_code
    if status == _HTTP_TOO_MANY_REQUESTS or status >= _HTTP_SERVER_ERROR:
        parameters = body.get("parameters")
        retry_after = parameters.get("retry_after") if isinstance(parameters, dict) else None
        raise TelegramTransientError(f"{method}: http {status}", retry_after)
    if not body.get("ok"):
        description = str(body.get("description", ""))
        raise TelegramPermanentError(
            _scrub(f"{method}: http {status} {description}".strip()), description
        )
    return body.get("result")


async def _send(
    client: httpx.AsyncClient,
    method: str,
    label: str,
    *,
    timeout: float,
    json_body: dict[str, Any] | None = None,
    data: dict[str, str] | None = None,
    files: dict[str, tuple[str, bytes, str]] | None = None,
) -> Any:
    try:
        result = await _call(
            client, method, timeout=timeout, json_body=json_body, data=data, files=files
        )
    except TelegramError as failure:
        logger.error("telegram %s failed: %s", label, failure)
        telegram_messages_total.add(1, {"method": label, "result": _result_label(failure)})
        raise
    telegram_messages_total.add(1, {"method": label, "result": "sent"})
    return result


def _sent(result: Any, kind: MessageKind) -> SentMessage:
    try:
        return SentMessage(
            chat_id=int(result["chat"]["id"]),
            message_id=int(result["message_id"]),
            kind=kind,
        )
    except (KeyError, TypeError, ValueError):
        raise TelegramPermanentError("unexpected reply shape from telegram") from None


def _caption(text: str) -> str:
    if len(text) > settings.TELEGRAM_CAPTION_MAX_CHARS:
        return text[: settings.TELEGRAM_CAPTION_MAX_CHARS - 3] + "..."
    return text


def _keyboard_field(reply_markup: dict[str, Any] | None) -> dict[str, str]:
    if not reply_markup:
        return {}
    return {"reply_markup": json.dumps(reply_markup, separators=(",", ":"))}


def _unconfigured(label: str) -> None:
    logger.warning("telegram not configured, skipping %s", label)
    telegram_messages_total.add(1, {"method": label, "result": "unconfigured"})


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


async def send_message(
    client: httpx.AsyncClient,
    text: str,
    reply_markup: dict[str, Any] | None = None,
    chat_id: int | str | None = None,
) -> SentMessage | None:
    if not is_configured():
        _unconfigured("message")
        return None
    body: dict[str, Any] = {
        "chat_id": chat_id if chat_id is not None else settings.TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
    }
    if reply_markup:
        body["reply_markup"] = reply_markup
    result = await _send(
        client,
        "sendMessage",
        "message",
        timeout=settings.TELEGRAM_REQUEST_TIMEOUT_SEC,
        json_body=body,
    )
    return _sent(result, MessageKind.TEXT)


async def send_photo(
    client: httpx.AsyncClient,
    image_path: str,
    caption: str = "",
    reply_markup: dict[str, Any] | None = None,
) -> SentMessage | None:
    if not is_configured():
        _unconfigured("photo")
        return None
    path = _resolve_media(image_path)
    if path is None:
        logger.warning("snapshot file not found, skipping photo path=%s", image_path)
        telegram_messages_total.add(1, {"method": "photo", "result": "snapshot_missing"})
        return None
    try:
        image = await asyncio.to_thread(path.read_bytes)
    except OSError as exc:
        logger.error("snapshot file read failed: %s", exc)
        telegram_messages_total.add(1, {"method": "photo", "result": "failed"})
        return None
    data = {
        "chat_id": str(settings.TELEGRAM_CHAT_ID),
        "caption": _caption(caption),
        "parse_mode": "HTML",
        **_keyboard_field(reply_markup),
    }
    result = await _send(
        client,
        "sendPhoto",
        "photo",
        timeout=settings.TELEGRAM_PHOTO_TIMEOUT_SEC,
        data=data,
        files={"photo": (path.name, image, "image/jpeg")},
    )
    return _sent(result, MessageKind.PHOTO)


async def send_video(
    client: httpx.AsyncClient,
    clip_path: str,
    cover_path: str | None,
    caption: str = "",
    width: int = 0,
    height: int = 0,
    reply_markup: dict[str, Any] | None = None,
) -> SentMessage | None:
    if not is_configured():
        _unconfigured("video")
        return None
    clip = _resolve_media(clip_path)
    if clip is None:
        return None
    cover = _resolve_media(cover_path) if cover_path else None
    try:
        size = clip.stat().st_size
        if size > settings.TELEGRAM_VIDEO_MAX_BYTES:
            logger.warning("clip over upload limit bytes=%d file=%s", size, clip.name)
            telegram_messages_total.add(1, {"method": "video", "result": "oversized"})
            return None
        video = await asyncio.to_thread(clip.read_bytes)
        cover_image = await asyncio.to_thread(cover.read_bytes) if cover else None
    except OSError as exc:
        logger.error("media file read failed: %s", exc)
        telegram_messages_total.add(1, {"method": "video", "result": "failed"})
        return None
    data = {
        "chat_id": str(settings.TELEGRAM_CHAT_ID),
        "caption": _caption(caption),
        "parse_mode": "HTML",
        "supports_streaming": "true",
        **_keyboard_field(reply_markup),
    }
    if width and height:
        data["width"] = str(width)
        data["height"] = str(height)
    files = {"video": (clip.name, video, "video/mp4")}
    if cover is not None and cover_image is not None:
        data["cover"] = "attach://cover"
        files["cover"] = (cover.name, cover_image, "image/jpeg")
    result = await _send(
        client,
        "sendVideo",
        "video",
        timeout=settings.TELEGRAM_CLIP_TIMEOUT_SEC,
        data=data,
        files=files,
    )
    return _sent(result, MessageKind.VIDEO)


async def edit_message(
    client: httpx.AsyncClient,
    chat_id: int,
    message_id: int,
    kind: MessageKind,
    text: str,
    reply_markup: dict[str, Any] | None = None,
) -> None:
    if kind == MessageKind.TEXT:
        method, field = "editMessageText", "text"
    else:
        method, field = "editMessageCaption", "caption"
    body: dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": message_id,
        field: _caption(text) if field == "caption" else text,
        "parse_mode": "HTML",
        "reply_markup": reply_markup or _REMOVE_KEYBOARD,
    }
    try:
        await _call(client, method, timeout=settings.TELEGRAM_REQUEST_TIMEOUT_SEC, json_body=body)
    except TelegramPermanentError as exc:
        if _NOT_MODIFIED in exc.description:
            telegram_messages_total.add(1, {"method": "edit", "result": "unchanged"})
            return
        logger.error("telegram edit failed: %s", exc)
        telegram_messages_total.add(1, {"method": "edit", "result": "permanent"})
        raise
    except TelegramError as exc:
        logger.error("telegram edit failed: %s", exc)
        telegram_messages_total.add(1, {"method": "edit", "result": _result_label(exc)})
        raise
    telegram_messages_total.add(1, {"method": "edit", "result": "sent"})


async def remove_keyboard(client: httpx.AsyncClient, chat_id: int, message_id: int) -> None:
    body = {"chat_id": chat_id, "message_id": message_id, "reply_markup": _REMOVE_KEYBOARD}
    try:
        await _call(
            client,
            "editMessageReplyMarkup",
            timeout=settings.TELEGRAM_REQUEST_TIMEOUT_SEC,
            json_body=body,
        )
    except TelegramError as exc:
        logger.warning("telegram keyboard removal failed: %s", exc)


async def delete_webhook(client: httpx.AsyncClient) -> None:
    await _call(
        client,
        "deleteWebhook",
        timeout=settings.TELEGRAM_REQUEST_TIMEOUT_SEC,
        json_body={"drop_pending_updates": False},
    )


async def answer_callback(
    client: httpx.AsyncClient,
    callback_query_id: str,
    text: str,
    show_alert: bool = False,
) -> bool:
    body = {"callback_query_id": callback_query_id, "text": text, "show_alert": show_alert}
    try:
        await _call(
            client,
            "answerCallbackQuery",
            timeout=settings.TELEGRAM_REQUEST_TIMEOUT_SEC,
            json_body=body,
        )
    except TelegramError as exc:
        logger.warning("telegram callback answer failed: %s", exc)
        telegram_messages_total.add(1, {"method": "answer", "result": _result_label(exc)})
        return False
    telegram_messages_total.add(1, {"method": "answer", "result": "sent"})
    return True


async def get_updates(
    client: httpx.AsyncClient, offset: int, timeout_sec: int
) -> list[dict[str, Any]]:
    body = {"offset": offset, "timeout": timeout_sec, "allowed_updates": _ALLOWED_UPDATES}
    result = await _call(
        client, "getUpdates", timeout=timeout_sec + _POLL_GRACE_SEC, json_body=body
    )
    if not isinstance(result, list):
        return []
    return [update for update in result if isinstance(update, dict)]


async def probe(client: httpx.AsyncClient) -> bool:
    if not is_configured():
        return False
    try:
        await _call(client, "getMe", timeout=settings.TELEGRAM_REQUEST_TIMEOUT_SEC)
    except TelegramError:
        return False
    return True
