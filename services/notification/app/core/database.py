from __future__ import annotations

import logging
from functools import lru_cache
from urllib.parse import quote_plus

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase

from app.shared.config import settings

logger = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None


@lru_cache(maxsize=1)
def _load_mongodb_password() -> str:
    path = settings.MONGODB_PASSWORD_FILE
    try:
        password = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        logger.error("mongodb password file missing at %s", path)
        return ""
    except OSError as exc:
        logger.error("mongodb password file unreadable at %s: %s", path, exc)
        return ""
    if not password:
        logger.error("mongodb password file empty at %s", path)
    return password


def _resolve_mongodb_url() -> str:
    user = quote_plus(settings.MONGODB_USER)
    password = quote_plus(_load_mongodb_password())
    ca_file = settings.MONGODB_CA_FILE
    return (
        f"mongodb://{user}:{password}@{settings.MONGODB_HOST}"
        f"/{settings.DATABASE_NAME}"
        f"?tls=true&tlsCAFile={ca_file}&authSource={settings.DATABASE_NAME}"
    )


async def connect_to_mongodb() -> None:
    global _client
    logger.info("connecting to mongodb")
    _client = AsyncIOMotorClient(_resolve_mongodb_url())
    await _client.admin.command("ping")
    logger.info("connected to mongodb")


async def close_mongodb_connection() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
        logger.info("mongodb connection closed")


def get_database() -> AsyncIOMotorDatabase:
    if _client is None:
        raise RuntimeError("mongodb client not initialized")
    return _client[settings.DATABASE_NAME]


def get_collection(name: str) -> AsyncIOMotorCollection:
    return get_database()[name]
