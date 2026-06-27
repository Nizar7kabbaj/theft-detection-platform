import logging

from fastapi import Request
from redis.asyncio import Redis, from_url

from .config import settings

logger = logging.getLogger(__name__)


def _resolve_redis_url() -> str:
    mode = (settings.REDIS_MODE or "local").lower()
    if mode == "cloud":
        return settings.REDIS_URL
    return settings.REDIS_URL_LOCAL


async def open_redis() -> Redis:
    mode = (settings.REDIS_MODE or "local").lower()
    logger.info("connecting to redis", extra={"mode": mode})
    client = from_url(
        _resolve_redis_url(),
        encoding="utf-8",
        decode_responses=True,
    )
    await client.ping()
    logger.info("connected to redis", extra={"mode": mode})
    return client


async def close_redis(client: Redis) -> None:
    await client.aclose()
    logger.info("redis connection closed")


def get_redis(request: Request) -> Redis:
    return request.app.state.redis
