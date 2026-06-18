import asyncio
import logging
import secrets
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app import telegram_service
from app.core.config import settings
from app.schemas.alertmanager import AlertmanagerWebhook

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@lru_cache(maxsize=1)
def _load_webhook_token() -> str:
    path = settings.ALERTMANAGER_WEBHOOK_TOKEN_FILE
    try:
        token = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        logger.error("webhook token file missing at %s", path)
        return ""
    except OSError as exc:
        logger.error("webhook token file unreadable at %s: %s", path, exc)
        return ""
    if not token:
        logger.error("webhook token file empty at %s", path)
    return token


def _reset_token_cache() -> None:
    _load_webhook_token.cache_clear()


async def require_bearer_token(request: Request) -> None:
    expected = _load_webhook_token()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="webhook token not configured",
        )
    header = request.headers.get("authorization", "")
    scheme, _, presented = header.partition(" ")
    if scheme.lower() != "bearer" or not presented:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
        )
    if not secrets.compare_digest(presented, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid bearer token",
        )


@router.post(
    "/alertmanager",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_bearer_token)],
)
async def receive_alertmanager(payload: AlertmanagerWebhook) -> None:
    if not telegram_service.is_configured():
        logger.error("telegram not configured, refusing webhook")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="telegram not configured",
        )

    message = payload.to_telegram_html()
    sent = await asyncio.to_thread(telegram_service.send_message, message)
    if not sent:
        logger.error(
            "telegram send failed for alertmanager group=%s status=%s",
            payload.group_key,
            payload.status,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="telegram send failed",
        )

    logger.info(
        "alertmanager webhook dispatched group=%s status=%s alerts=%d",
        payload.group_key,
        payload.status,
        len(payload.alerts),
    )
