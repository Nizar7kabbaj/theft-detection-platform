from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import grpc
import pytest

from app.server.grpc_gen import auth_pb2, common_pb2, decision_pb2
from app.shared import decision_token
from app.shared.decision_token import ButtonDecision, sign
from app.shared.schemas.delivery import DeliveryIntent
from app.telegram import handlers

pytestmark = pytest.mark.unit

CHAT = -100
MESSAGE = 55
OTHER_MESSAGE = 56
INTENT = "65f0c0ffee0000000000abcd"
OPERATOR = 777


class FakeRedis:
    def __init__(self) -> None:
        self.keys: set[str] = set()

    async def set(
        self, key: str, _value: str, nx: bool = False, ex: int | None = None
    ) -> bool | None:
        if nx and key in self.keys:
            return None
        self.keys.add(key)
        return True


class FakeIntents:
    def __init__(self, intents: dict[str, DeliveryIntent]) -> None:
        self._intents = intents

    async def get_by_id(self, intent_id: str) -> DeliveryIntent | None:
        return self._intents.get(intent_id)


class FakeDecisions:
    def __init__(self) -> None:
        self.requests: list[decision_pb2.DecideAlertRequest] = []
        self.reply = decision_pb2.DecideAlertReply(
            outcome=decision_pb2.DECIDE_OUTCOME_DECIDED, decision=common_pb2.DECISION_CONFIRMED
        )
        self.error: grpc.aio.AioRpcError | None = None

    async def DecideAlert(
        self, request: decision_pb2.DecideAlertRequest, timeout: float | None = None
    ) -> decision_pb2.DecideAlertReply:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.reply


class FakeAuth:
    def __init__(self) -> None:
        self.reply = auth_pb2.BindTelegramReply(
            status=auth_pb2.BIND_TELEGRAM_STATUS_BOUND, username="<ws>admin"
        )

    async def BindTelegram(
        self, request: auth_pb2.BindTelegramRequest, timeout: float | None = None
    ) -> auth_pb2.BindTelegramReply:
        return self.reply


@pytest.fixture(autouse=True)
def key_and_chat(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    key = tmp_path / "callback_key"
    key.write_text("33" * 32, encoding="ascii")
    monkeypatch.setattr(decision_token.settings, "TELEGRAM_CALLBACK_KEY_FILE", key)
    monkeypatch.setattr(handlers.settings, "TELEGRAM_CHAT_ID", str(CHAT))
    decision_token._key.cache_clear()
    yield
    decision_token._key.cache_clear()


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    recorded: list[tuple[Any, ...]] = []

    async def answer(_client: Any, _callback_id: str, text: str, show_alert: bool = False) -> bool:
        recorded.append(("answer", text, show_alert))
        return True

    async def remove(_client: Any, chat_id: int, message_id: int) -> None:
        recorded.append(("remove", chat_id, message_id))

    async def send(_client: Any, text: str, reply_markup: Any = None, chat_id: Any = None) -> None:
        recorded.append(("send", text, chat_id))

    monkeypatch.setattr(handlers, "answer_callback", answer)
    monkeypatch.setattr(handlers, "remove_keyboard", remove)
    monkeypatch.setattr(handlers, "send_message", send)
    return recorded


@pytest.fixture
def decisions() -> FakeDecisions:
    return FakeDecisions()


@pytest.fixture
def resyncs() -> list[tuple[str, ...]]:
    return []


@pytest.fixture
def ctx(decisions: FakeDecisions, resyncs: list[tuple[str, ...]]) -> handlers.Context:
    now = datetime(2026, 10, 7, tzinfo=UTC)
    intent = DeliveryIntent.model_validate(
        {
            "_id": INTENT,
            "source": "alert",
            "source_ref": "cam-a-1-28409-3",
            "channel": "telegram",
            "recipient": str(CHAT),
            "payload": {},
            "status": "sent",
            "attempts": 1,
            "created_at": now,
            "updated_at": now,
            "telegram": {"chat_id": CHAT, "message_id": MESSAGE, "kind": "video"},
        }
    )

    async def resync(*args: str) -> None:
        resyncs.append(args)

    return handlers.Context(
        telegram=None,
        decisions=decisions,
        auth=FakeAuth(),
        redis=FakeRedis(),
        intents=FakeIntents({INTENT: intent}),
        resync=resync,
    )


def _press(
    update_id: int,
    data: str,
    chat: int = CHAT,
    message: int = MESSAGE,
    sender: int = OPERATOR,
) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": f"cb-{update_id}",
            "from": {"id": sender},
            "message": {"message_id": message, "chat": {"id": chat}},
            "data": data,
        },
    }


def _valid(decision: ButtonDecision = ButtonDecision.CONFIRMED) -> str:
    return sign(INTENT, decision)


def _rpc_error(code: grpc.StatusCode) -> grpc.aio.AioRpcError:
    return grpc.aio.AioRpcError(code, grpc.aio.Metadata(), grpc.aio.Metadata(), "down")


async def test_a_valid_press_decides_through_the_backend(
    ctx: handlers.Context, decisions: FakeDecisions, calls: list[tuple[Any, ...]]
) -> None:
    await handlers.handle_update(ctx, _press(1, _valid()))
    request = decisions.requests[0]
    assert request.alert_id == "cam-a-1-28409-3"
    assert request.decision == common_pb2.DECISION_CONFIRMED
    assert request.telegram_user_id == OPERATOR
    assert calls == [("answer", "recorded: confirmed", False)]


async def test_already_decided_answers_the_existing_decision_and_resyncs(
    ctx: handlers.Context,
    decisions: FakeDecisions,
    calls: list[tuple[Any, ...]],
    resyncs: list[tuple[str, ...]],
) -> None:
    decisions.reply = decision_pb2.DecideAlertReply(
        outcome=decision_pb2.DECIDE_OUTCOME_ALREADY_DECIDED,
        decision=common_pb2.DECISION_CONFIRMED,
        decided_by="ws-admin",
    )
    decisions.reply.decided_at.FromDatetime(datetime(2026, 10, 7, 11, 43, tzinfo=UTC))
    await handlers.handle_update(ctx, _press(2, _valid(ButtonDecision.DISMISSED)))
    assert calls == [("answer", "already confirmed by ws-admin", False)]
    assert resyncs == [
        ("cam-a-1-28409-3", "DECISION_CONFIRMED", "ws-admin", "2026-10-07T11:43:00+00:00")
    ]


async def test_tampered_button_never_reaches_the_backend(
    ctx: handlers.Context, decisions: FakeDecisions, calls: list[tuple[Any, ...]]
) -> None:
    token = _valid()
    middle = len(token) // 2
    forged = token[:middle] + ("A" if token[middle] != "A" else "B") + token[middle + 1 :]
    await handlers.handle_update(ctx, _press(3, forged))
    assert decisions.requests == []
    assert calls == [("answer", "not accepted", False)]


async def test_expired_button_answers_and_drops_the_keyboard(
    ctx: handlers.Context, decisions: FakeDecisions, calls: list[tuple[Any, ...]]
) -> None:
    old = sign(INTENT, ButtonDecision.CONFIRMED, now=1_000)
    await handlers.handle_update(ctx, _press(4, old))
    assert decisions.requests == []
    assert calls == [
        ("answer", "this button expired, decide in the console", False),
        ("remove", CHAT, MESSAGE),
    ]


async def test_valid_button_on_another_message_is_refused(
    ctx: handlers.Context, decisions: FakeDecisions, calls: list[tuple[Any, ...]]
) -> None:
    await handlers.handle_update(ctx, _press(5, _valid(), message=OTHER_MESSAGE))
    assert decisions.requests == []
    assert calls == [("answer", "not accepted", False)]


async def test_press_from_another_chat_is_refused(
    ctx: handlers.Context, decisions: FakeDecisions, calls: list[tuple[Any, ...]]
) -> None:
    await handlers.handle_update(ctx, _press(6, _valid(), chat=1))
    assert decisions.requests == []
    assert calls == [("answer", "not accepted", False)]


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (
            decision_pb2.DECIDE_OUTCOME_OPERATOR_UNKNOWN,
            [("answer", "your telegram account is not linked to an operator", True)],
        ),
        (
            decision_pb2.DECIDE_OUTCOME_OPERATOR_FORBIDDEN,
            [("answer", "your account cannot decide alerts", True)],
        ),
        (
            decision_pb2.DECIDE_OUTCOME_ALERT_NOT_FOUND,
            [("answer", "this alert no longer exists", False), ("remove", CHAT, MESSAGE)],
        ),
    ],
)
async def test_backend_refusals_are_explained(
    ctx: handlers.Context,
    decisions: FakeDecisions,
    calls: list[tuple[Any, ...]],
    outcome: int,
    expected: list[tuple[Any, ...]],
) -> None:
    decisions.reply = decision_pb2.DecideAlertReply(outcome=outcome)
    await handlers.handle_update(ctx, _press(7, _valid()))
    assert calls == expected


async def test_backend_down_asks_to_try_again(
    ctx: handlers.Context, decisions: FakeDecisions, calls: list[tuple[Any, ...]]
) -> None:
    decisions.error = _rpc_error(grpc.StatusCode.UNAVAILABLE)
    await handlers.handle_update(ctx, _press(8, _valid()))
    assert calls == [("answer", "not recorded, try again", False)]


async def test_a_replayed_update_is_handled_once(
    ctx: handlers.Context, decisions: FakeDecisions, calls: list[tuple[Any, ...]]
) -> None:
    update = _press(9, _valid())
    await handlers.handle_update(ctx, update)
    await handlers.handle_update(ctx, update)
    assert len(decisions.requests) == 1
    assert len(calls) == 1


def _start(update_id: int, text: str, chat_type: str = "private") -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "chat": {"id": 4242, "type": chat_type},
            "from": {"id": OPERATOR},
            "text": text,
        },
    }


async def test_start_with_a_token_links_and_escapes_the_username(
    ctx: handlers.Context, calls: list[tuple[Any, ...]]
) -> None:
    await handlers.handle_update(ctx, _start(10, "/start " + "a" * 43))
    assert calls == [
        ("send", "linked to &lt;ws&gt;admin. decisions from here carry that name.", 4242)
    ]


async def test_start_without_a_token_points_to_the_console(
    ctx: handlers.Context, calls: list[tuple[Any, ...]]
) -> None:
    await handlers.handle_update(ctx, _start(11, "/start"))
    assert calls == [("send", "open the link from the console to connect this account.", 4242)]


async def test_start_in_a_group_is_ignored(
    ctx: handlers.Context, calls: list[tuple[Any, ...]]
) -> None:
    await handlers.handle_update(ctx, _start(12, "/start " + "a" * 43, chat_type="group"))
    assert calls == []
