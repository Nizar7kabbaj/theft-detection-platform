import logging
from functools import lru_cache
from urllib.parse import quote_plus

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import AsyncMongoClient

from app.core.config import settings

logger = logging.getLogger(__name__)
client: AsyncIOMotorClient | None = None
_probe_client: AsyncMongoClient | None = None


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


async def connect_to_mongodb():
    global client
    logger.info("connecting to mongodb")
    client = AsyncIOMotorClient(_resolve_mongodb_url(), tz_aware=True)
    logger.info("connected to mongodb")


async def ping_mongodb() -> None:
    global _probe_client
    if _probe_client is None:
        _probe_client = AsyncMongoClient(
            _resolve_mongodb_url(),
            serverSelectionTimeoutMS=1000,
            connectTimeoutMS=1000,
            maxPoolSize=1,
            appname="backend-health",
        )
    await _probe_client.admin.command("ping")


async def close_mongodb_connection():
    global client, _probe_client
    if _probe_client is not None:
        await _probe_client.close()
        _probe_client = None
    if client:
        client.close()
        client = None
        logger.info("mongodb connection closed")


def get_database():
    return client[settings.DATABASE_NAME]
