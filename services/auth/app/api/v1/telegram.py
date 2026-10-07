from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from redis.exceptions import RedisError

from app.core.authz import Actor, current_actor
from app.core.config import get_settings
from app.core.csrf import csrf_protect
from app.core.database import get_sessionmaker
from app.core.redis import store_telegram_link
from app.core.telegram_link import hash_link_token, new_link_token
from app.repositories.audit_outbox_repository import AuditOutboxRepository
from app.repositories.telegram_binding_repository import TelegramBindingRepository
from app.schemas.telegram import TelegramLinkResponse, TelegramStatus
from app.services import audit_service as audit_events

router = APIRouter(prefix="/auth/telegram", tags=["telegram"])

_NOT_CONFIGURED = "telegram linking is not configured"
_STORE_UNAVAILABLE = "link store unavailable"


@router.get("", response_model=TelegramStatus)
async def telegram_status(actor: Annotated[Actor, Depends(current_actor)]) -> TelegramStatus:
    factory = get_sessionmaker()
    async with factory() as db:
        binding = await TelegramBindingRepository(db).get_for_user(actor.user_id)
    if binding is None:
        return TelegramStatus(linked=False)
    return TelegramStatus(linked=True, linked_at=binding.created_at)


@router.post("/link", response_model=TelegramLinkResponse, status_code=status.HTTP_201_CREATED)
async def issue_link(
    response: Response,
    actor: Annotated[Actor, Depends(current_actor)],
    _: Annotated[None, Depends(csrf_protect)],
) -> TelegramLinkResponse:
    settings = get_settings()
    if not settings.telegram_bot_username:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_NOT_CONFIGURED)
    token = new_link_token()
    ttl = settings.telegram_link_ttl_seconds
    try:
        await store_telegram_link(actor.user_id, hash_link_token(token), ttl)
    except RedisError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_STORE_UNAVAILABLE
        ) from exc
    response.headers["Cache-Control"] = "no-store"
    return TelegramLinkResponse(
        url=f"https://t.me/{settings.telegram_bot_username}?start={token}",
        expires_at=datetime.now(UTC) + timedelta(seconds=ttl),
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def unlink(
    actor: Annotated[Actor, Depends(current_actor)],
    _: Annotated[None, Depends(csrf_protect)],
) -> Response:
    factory = get_sessionmaker()
    async with factory() as db:
        previous = await TelegramBindingRepository(db).unbind(actor.user_id)
        if previous is not None:
            event = audit_events.telegram_link_changed(
                actor_user_id=actor.user_id, before=previous, after=None
            )
            await AuditOutboxRepository(db).enqueue(
                event.event_id, event.event_bytes, event.occurred_at
            )
        await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
