from __future__ import annotations

import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo import ASCENDING

from app.shared.config import settings

logger = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None


def _resolve_mongodb_url() -> str:
    mode = (settings.MONGODB_MODE or "local").lower()
    if mode == "atlas":
        return settings.MONGODB_URL
    return settings.MONGODB_URL_LOCAL


async def connect_to_mongodb() -> None:
    global _client
    mode = (settings.MONGODB_MODE or "local").lower()
    logger.info("connecting to mongodb mode=%s", mode)
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


async def ensure_indexes() -> None:
    intents = get_collection(settings.DELIVERY_INTENT_COLLECTION)
    name = await intents.create_index(
        [
            ("source", ASCENDING),
            ("source_ref", ASCENDING),
            ("channel", ASCENDING),
            ("recipient", ASCENDING),
        ],
        unique=True,
        name="uniq_delivery_natural_key",
    )
    logger.info("ensured index %s", name)
