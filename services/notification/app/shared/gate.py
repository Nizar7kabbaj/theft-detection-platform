from __future__ import annotations

import logging
from datetime import UTC, datetime

import redis

from app.shared.config import settings

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None


def _redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(
            settings.NOTIFY_REDIS_URL,
            socket_connect_timeout=2.0,
            socket_timeout=2.0,
            decode_responses=True,
        )
    return _client


def gate_set(reason: str) -> None:
    stamp = datetime.now(UTC).isoformat()
    value = f"{stamp} {reason}"
    _redis().set(settings.GATE_KEY, value, ex=settings.GATE_TTL_SEC)
    logger.warning("delivery gate raised: %s", reason)


def gate_refresh() -> None:
    _redis().expire(settings.GATE_KEY, settings.GATE_TTL_SEC)


def gate_clear() -> None:
    _redis().delete(settings.GATE_KEY)
    logger.info("delivery gate cleared")


def gate_is_raised() -> bool:
    return _redis().exists(settings.GATE_KEY) == 1


def gate_ttl() -> int:
    return _redis().ttl(settings.GATE_KEY)
