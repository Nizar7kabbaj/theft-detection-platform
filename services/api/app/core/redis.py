import logging
from functools import lru_cache
from urllib.parse import quote_plus

from fastapi import Request
from redis.asyncio import Redis, from_url

from app.core.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _load_redis_password() -> str:
    path = settings.REDIS_PASSWORD_FILE
    try:
        password = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        logger.error("redis password file missing at %s", path)
        return ""
    except OSError as exc:
        logger.error("redis password file unreadable at %s: %s", path, exc)
        return ""
    if not password:
        logger.error("redis password file empty at %s", path)
    return password


def _resolve_redis_url() -> str:
    mode = (settings.REDIS_MODE or "local").lower()
    if mode == "cloud":
        return settings.REDIS_URL
    user = quote_plus(settings.REDIS_USER)
    password = quote_plus(_load_redis_password())
    return (
        f"redis://{user}:{password}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"
    )


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
