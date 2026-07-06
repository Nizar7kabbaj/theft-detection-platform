from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests
from pydantic import SecretStr

from app.shared import telegram_service

pytestmark = pytest.mark.unit


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        telegram_service.settings, "TELEGRAM_BOT_TOKEN", SecretStr("bot-token")
    )
    monkeypatch.setattr(telegram_service.settings, "TELEGRAM_CHAT_ID", "123456")


@pytest.fixture
def snapshot(tmp_path: Path) -> str:
    path = tmp_path / "snap.jpg"
    path.write_bytes(b"\xff\xd8\xff\xd9")
    return str(path)


def _ok() -> MagicMock:
    response = MagicMock()
    response.raise_for_status.return_value = None
    return response


def test_is_configured_reflects_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(telegram_service.settings, "TELEGRAM_BOT_TOKEN", None)
    assert telegram_service.is_configured() is False


def test_send_message_unconfigured_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(telegram_service.settings, "TELEGRAM_BOT_TOKEN", None)
    post = MagicMock()
    monkeypatch.setattr(telegram_service.requests, "post", post)
    assert telegram_service.send_message("hi") is False
    post.assert_not_called()


def test_send_message_success_returns_true(
    configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    post = MagicMock(return_value=_ok())
    monkeypatch.setattr(telegram_service.requests, "post", post)
    assert telegram_service.send_message("hi") is True
    url = post.call_args.args[0]
    payload = post.call_args.kwargs["json"]
    assert "sendMessage" in url
    assert payload["chat_id"] == "123456"
    assert payload["text"] == "hi"
    assert payload["parse_mode"] == "HTML"


def test_send_message_reraises_on_request_exception(
    configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    post = MagicMock(side_effect=requests.exceptions.RequestException("net"))
    monkeypatch.setattr(telegram_service.requests, "post", post)
    with pytest.raises(requests.exceptions.RequestException):
        telegram_service.send_message("hi")


def test_send_photo_unconfigured_returns_false(
    snapshot: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(telegram_service.settings, "TELEGRAM_BOT_TOKEN", None)
    post = MagicMock()
    monkeypatch.setattr(telegram_service.requests, "post", post)
    assert telegram_service.send_photo(snapshot, "cap") is False
    post.assert_not_called()


def test_send_photo_missing_file_returns_false(
    configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    post = MagicMock()
    monkeypatch.setattr(telegram_service.requests, "post", post)
    assert telegram_service.send_photo("/nope/missing.jpg", "cap") is False
    post.assert_not_called()


def test_send_photo_success_returns_true(
    configured: None, snapshot: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    post = MagicMock(return_value=_ok())
    monkeypatch.setattr(telegram_service.requests, "post", post)
    assert telegram_service.send_photo(snapshot, "cap") is True
    assert "sendPhoto" in post.call_args.args[0]


def test_send_photo_truncates_long_caption(
    configured: None, snapshot: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(telegram_service.settings, "TELEGRAM_CAPTION_MAX_CHARS", 10)
    post = MagicMock(return_value=_ok())
    monkeypatch.setattr(telegram_service.requests, "post", post)
    telegram_service.send_photo(snapshot, "x" * 50)
    caption = post.call_args.kwargs["data"]["caption"]
    assert len(caption) == 10
    assert caption.endswith("...")


def test_send_photo_reraises_on_request_exception(
    configured: None, snapshot: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    post = MagicMock(side_effect=requests.exceptions.RequestException("net"))
    monkeypatch.setattr(telegram_service.requests, "post", post)
    with pytest.raises(requests.exceptions.RequestException):
        telegram_service.send_photo(snapshot, "cap")
