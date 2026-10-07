from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest

from app.shared import telegram_service
from app.shared.telegram_service import (
    MessageKind,
    TelegramPermanentError,
    TelegramTransientError,
    TelegramUnreachableError,
)

pytestmark = pytest.mark.unit

Handler = Callable[[httpx.Request], httpx.Response]


def _ok(message_id: int = 7, chat_id: int = -100) -> httpx.Response:
    return httpx.Response(
        200, json={"ok": True, "result": {"message_id": message_id, "chat": {"id": chat_id}}}
    )


def _client(handler: Handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url="https://api.telegram.org/botSECRET/", transport=httpx.MockTransport(handler)
    )


@pytest.fixture(autouse=True)
def clear_token_cache() -> Iterator[None]:
    telegram_service._token.cache_clear()
    yield
    telegram_service._token.cache_clear()


@pytest.fixture
def snapshots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "snapshots"
    folder.mkdir()
    monkeypatch.setattr(telegram_service.settings, "SNAPSHOTS_DIR", str(folder))
    return folder


@pytest.fixture
def configured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, snapshots: Path) -> Path:
    token_file = tmp_path / "telegram_bot_token"
    token_file.write_text("bot-token", encoding="utf-8")
    monkeypatch.setattr(telegram_service.settings, "TELEGRAM_BOT_TOKEN_FILE", token_file)
    monkeypatch.setattr(telegram_service.settings, "TELEGRAM_CHAT_ID", "-100")
    return snapshots


def test_is_configured_false_without_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(telegram_service.settings, "TELEGRAM_BOT_TOKEN_FILE", tmp_path / "absent")
    monkeypatch.setattr(telegram_service.settings, "TELEGRAM_CHAT_ID", "-100")
    assert telegram_service.is_configured() is False


def test_is_configured_false_without_chat_id(
    configured: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(telegram_service.settings, "TELEGRAM_CHAT_ID", None)
    assert telegram_service.is_configured() is False


def test_is_configured_true_when_both_present(configured: Path) -> None:
    assert telegram_service.is_configured() is True


async def test_send_message_returns_the_handle_and_sends_the_keyboard(configured: Path) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _ok(message_id=41)

    keyboard = {"inline_keyboard": [[{"text": "confirmed", "callback_data": "x"}]]}
    async with _client(handler) as client:
        sent = await telegram_service.send_message(client, "hello", reply_markup=keyboard)
    assert sent == telegram_service.SentMessage(chat_id=-100, message_id=41, kind=MessageKind.TEXT)
    body = json.loads(seen[0].content)
    assert seen[0].url.path.endswith("/sendMessage")
    assert body["reply_markup"] == keyboard
    assert body["parse_mode"] == "HTML"


async def test_send_photo_outside_the_snapshot_folder_is_refused(
    configured: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"\xff\xd8\xff\xd9")

    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request expected")

    async with _client(handler) as client:
        assert await telegram_service.send_photo(client, "../outside.jpg", "cap") is None


async def test_send_photo_truncates_a_long_caption(configured: Path) -> None:
    (configured / "snap.jpg").write_bytes(b"\xff\xd8\xff\xd9")
    seen: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.content)
        return _ok()

    async with _client(handler) as client:
        sent = await telegram_service.send_photo(client, "snap.jpg", "x" * 2000)
    assert sent is not None
    assert sent.kind is MessageKind.PHOTO
    assert b"x" * 1021 + b"..." in seen[0]
    assert b"x" * 1022 not in seen[0]


async def test_send_video_attaches_cover_and_keyboard(configured: Path) -> None:
    (configured / "clip.mp4").write_bytes(b"\x00" * 64)
    (configured / "snap.jpg").write_bytes(b"\xff\xd8\xff\xd9")
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _ok(message_id=99)

    keyboard = {"inline_keyboard": [[{"text": "confirmed", "callback_data": "x"}]]}
    async with _client(handler) as client:
        sent = await telegram_service.send_video(
            client, "clip.mp4", "snap.jpg", "prompt", reply_markup=keyboard
        )
    assert sent == telegram_service.SentMessage(chat_id=-100, message_id=99, kind=MessageKind.VIDEO)
    content = seen[0].content
    assert seen[0].url.path.endswith("/sendVideo")
    assert b'name="cover"' in content
    assert b"attach://cover" in content
    assert b'name="reply_markup"' in content


async def test_send_video_over_the_upload_limit_is_skipped(
    configured: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (configured / "clip.mp4").write_bytes(b"\x00" * 64)
    monkeypatch.setattr(telegram_service.settings, "TELEGRAM_VIDEO_MAX_BYTES", 10)

    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request expected")

    async with _client(handler) as client:
        assert await telegram_service.send_video(client, "clip.mp4", None, "prompt") is None


async def test_rate_limit_is_transient_and_keeps_retry_after(configured: Path) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"ok": False, "parameters": {"retry_after": 3}})

    async with _client(handler) as client:
        with pytest.raises(TelegramTransientError) as caught:
            await telegram_service.send_message(client, "hello")
    assert caught.value.retry_after == 3


async def test_server_error_is_transient(configured: Path) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="bad gateway")

    async with _client(handler) as client:
        with pytest.raises(TelegramTransientError):
            await telegram_service.send_message(client, "hello")


async def test_client_error_is_permanent_and_never_shows_the_token(configured: Path) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400, json={"ok": False, "description": "bad request near /botSECRET/sendMessage"}
        )

    async with _client(handler) as client:
        with pytest.raises(TelegramPermanentError) as caught:
            await telegram_service.send_message(client, "hello")
    assert "SECRET" not in str(caught.value)
    assert "<redacted>" in str(caught.value)


async def test_transport_failure_is_unreachable_and_never_shows_the_token(
    configured: Path,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    async with _client(handler) as client:
        with pytest.raises(TelegramUnreachableError) as caught:
            await telegram_service.send_message(client, "hello")
    assert "SECRET" not in str(caught.value)


async def test_edit_removes_the_keyboard_and_tolerates_not_modified() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            400, json={"ok": False, "description": "Bad Request: message is not modified"}
        )

    async with _client(handler) as client:
        await telegram_service.edit_message(client, -100, 7, MessageKind.VIDEO, "decided")
    body = json.loads(seen[0].content)
    assert seen[0].url.path.endswith("/editMessageCaption")
    assert body["reply_markup"] == {"inline_keyboard": []}


async def test_edit_on_a_text_message_uses_edit_text() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True, "result": True})

    async with _client(handler) as client:
        await telegram_service.edit_message(client, -100, 7, MessageKind.TEXT, "decided")
    assert seen[0].url.path.endswith("/editMessageText")
    assert json.loads(seen[0].content)["text"] == "decided"


async def test_answer_callback_reports_failure_without_raising() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"ok": False, "description": "query is too old"})

    async with _client(handler) as client:
        assert await telegram_service.answer_callback(client, "cb-1", "recorded") is False


async def test_get_updates_keeps_only_objects() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True, "result": [{"update_id": 5}, "junk", 3]})

    async with _client(handler) as client:
        assert await telegram_service.get_updates(client, 0, 1) == [{"update_id": 5}]
