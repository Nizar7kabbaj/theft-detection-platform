import logging
from motor.motor_asyncio import AsyncIOMotorClient
from .config import settings


logger = logging.getLogger(__name__)
client: AsyncIOMotorClient = None


def _resolve_mongodb_url() -> str:
    return settings.MONGODB_URL_LOCAL

async def connect_to_mongodb():
    global client
    logger.info("connecting to mongodb")
    client = AsyncIOMotorClient(_resolve_mongodb_url())
    logger.info("connected to mongodb")


async def close_mongodb_connection():
    global client
    if client:
        client.close()
        logger.info("mongodb connection closed")


def get_database():
    return client[settings.DATABASE_NAME]
