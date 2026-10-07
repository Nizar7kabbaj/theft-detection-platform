from __future__ import annotations

import html
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC
from typing import Any

import grpc
import httpx
from redis.asyncio import Redis

from app.repositories.delivery_intent import DeliveryIntentRepository
from app.server.grpc_gen import auth_pb2, common_pb2, decision_pb2
from app.server.grpc_gen.auth_pb2_grpc import AuthServiceStub
from app.server.grpc_gen.decision_pb2_grpc import AlertDecisionServiceStub
from app.shared.config import settings
from app.shared.decision_token import DecisionTokenError, verify
from app.shared.metrics import telegram_callbacks_total
from app.shared.telegram_service import answer_callback, remove_keyboard, send_message

logger = logging.getLogger(__name__)

_START_PARTS = 2
_LABELS = {
    common_pb2.DECISION_CONFIRMED: "confirmed",
    common_pb2.DECISION_DISMISSED: "dismissed",
    common_pb2.DECISION_UNSURE: "unsure",
}
_BIND_REPLIES = {
    auth_pb2.BIND_TELEGRAM_STATUS_TOKEN_INVALID: (
        "this link is invalid or expired. create a new one from the console."
    ),
    auth_pb2.BIND_TELEGRAM_STATUS_ACCOUNT_IN_USE: (
        "this telegram account is already linked to another user."
    ),
}

Resync = Callable[[str, str, str, str], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class Context:
    telegram: httpx.AsyncClient
    decisions: AlertDecisionServiceStub
    auth: AuthServiceStub
    redis: Redis
    intents: DeliveryIntentRepository
    resync: Resync


def _count(outcome: str) -> None:
    telegram_callbacks_total.add(1, {"outcome": outcome})


async def _first_time(ctx: Context, update_id: int) -> bool:
    key = f"notify:telegram:update:{update_id}"
    return bool(await ctx.redis.set(key, "1", nx=True, ex=settings.POLLER_UPDATE_DEDUPE_TTL_SEC))


async def _refuse(ctx: Context, callback_id: str, outcome: str) -> None:
    _count(outcome)
    await answer_callback(ctx.telegram, callback_id, "not accepted")


async def _resync(ctx: Context, reply: decision_pb2.DecideAlertReply, alert_id: str) -> None:
    if not reply.HasField("decided_at"):
        return
    decided_at = reply.decided_at.ToDatetime(tzinfo=UTC)
    await ctx.resync(
        alert_id,
        common_pb2.Decision.Name(reply.decision),
        reply.decided_by,
        decided_at.isoformat(),
    )


async def _press(ctx: Context, query: dict[str, Any]) -> None:
    callback_id = str(query.get("id", ""))
    message = query.get("message")
    sender = query.get("from")
    if not callback_id or not isinstance(message, dict) or not isinstance(sender, dict):
        logger.warning("callback refused reason=malformed_update")
        _count("malformed")
        return
    chat_id = int(message.get("chat", {}).get("id", 0))
    message_id = int(message.get("message_id", 0))
    if str(chat_id) != str(settings.TELEGRAM_CHAT_ID):
        logger.warning("callback refused reason=wrong_chat")
        await _refuse(ctx, callback_id, "wrong_chat")
        return
    try:
        claim = verify(str(query.get("data", "")))
    except DecisionTokenError as exc:
        if exc.reason == "expired":
            _count("expired")
            await answer_callback(
                ctx.telegram, callback_id, "this button expired, decide in the console"
            )
            await remove_keyboard(ctx.telegram, chat_id, message_id)
            return
        logger.warning("callback refused reason=%s", exc.reason)
        await _refuse(ctx, callback_id, exc.reason)
        return
    intent = await ctx.intents.get_by_id(claim.intent_id)
    ref = None if intent is None else intent.telegram
    if intent is None or ref is None or ref.chat_id != chat_id or ref.message_id != message_id:
        logger.warning("callback refused reason=message_mismatch")
        await _refuse(ctx, callback_id, "message_mismatch")
        return
    request = decision_pb2.DecideAlertRequest(
        alert_id=intent.source_ref,
        decision=common_pb2.Decision.Value(claim.decision.wire),
        telegram_user_id=int(sender.get("id", 0)),
    )
    try:
        reply = await ctx.decisions.DecideAlert(request, timeout=settings.DECISION_CALL_TIMEOUT_SEC)
    except grpc.aio.AioRpcError as exc:
        logger.warning("decide alert failed code=%s", exc.code().name)
        _count("backend_unavailable")
        await answer_callback(ctx.telegram, callback_id, "not recorded, try again")
        return
    await _answer_outcome(ctx, callback_id, chat_id, message_id, intent.source_ref, reply)


async def _answer_outcome(
    ctx: Context,
    callback_id: str,
    chat_id: int,
    message_id: int,
    alert_id: str,
    reply: decision_pb2.DecideAlertReply,
) -> None:
    label = _LABELS.get(reply.decision, "decided")
    outcome = reply.outcome
    if outcome == decision_pb2.DECIDE_OUTCOME_DECIDED:
        _count("decided")
        await answer_callback(ctx.telegram, callback_id, f"recorded: {label}")
    elif outcome == decision_pb2.DECIDE_OUTCOME_ALREADY_DECIDED:
        _count("already_decided")
        who = f" by {reply.decided_by}" if reply.decided_by else ""
        await answer_callback(ctx.telegram, callback_id, f"already {label}{who}")
        await _resync(ctx, reply, alert_id)
    elif outcome == decision_pb2.DECIDE_OUTCOME_ALERT_NOT_FOUND:
        _count("alert_not_found")
        await answer_callback(ctx.telegram, callback_id, "this alert no longer exists")
        await remove_keyboard(ctx.telegram, chat_id, message_id)
    elif outcome == decision_pb2.DECIDE_OUTCOME_OPERATOR_UNKNOWN:
        _count("not_linked")
        await answer_callback(
            ctx.telegram,
            callback_id,
            "your telegram account is not linked to an operator",
            show_alert=True,
        )
    elif outcome == decision_pb2.DECIDE_OUTCOME_OPERATOR_FORBIDDEN:
        _count("forbidden")
        await answer_callback(
            ctx.telegram, callback_id, "your account cannot decide alerts", show_alert=True
        )
    else:
        _count("unexpected_outcome")
        await answer_callback(ctx.telegram, callback_id, "not recorded, try again")


async def _start(ctx: Context, message: dict[str, Any]) -> None:
    chat = message.get("chat")
    sender = message.get("from")
    text = str(message.get("text", ""))
    if not isinstance(chat, dict) or not isinstance(sender, dict):
        return
    if chat.get("type") != "private" or not text.startswith("/start"):
        return
    chat_id = int(chat.get("id", 0))
    parts = text.split(maxsplit=1)
    if len(parts) != _START_PARTS:
        await send_message(
            ctx.telegram, "open the link from the console to connect this account.", chat_id=chat_id
        )
        return
    request = auth_pb2.BindTelegramRequest(
        link_token=parts[1].strip(), telegram_user_id=int(sender.get("id", 0))
    )
    try:
        reply = await ctx.auth.BindTelegram(request, timeout=settings.DECISION_CALL_TIMEOUT_SEC)
    except grpc.aio.AioRpcError as exc:
        logger.warning("telegram bind failed code=%s", exc.code().name)
        _count("bind_unavailable")
        await send_message(ctx.telegram, "linking is unavailable, try again.", chat_id=chat_id)
        return
    if reply.status == auth_pb2.BIND_TELEGRAM_STATUS_BOUND:
        _count("bound")
        await send_message(
            ctx.telegram,
            f"linked to {html.escape(reply.username)}. decisions from here carry that name.",
            chat_id=chat_id,
        )
        return
    _count("bind_refused")
    reply_text = _BIND_REPLIES.get(reply.status, "linking failed, create a new link.")
    await send_message(ctx.telegram, reply_text, chat_id=chat_id)


async def handle_update(ctx: Context, update: dict[str, Any]) -> None:
    update_id = int(update.get("update_id", 0))
    if update_id <= 0 or not await _first_time(ctx, update_id):
        return
    query = update.get("callback_query")
    if isinstance(query, dict):
        await _press(ctx, query)
        return
    message = update.get("message")
    if isinstance(message, dict):
        await _start(ctx, message)
