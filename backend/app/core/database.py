from motor.motor_asyncio import AsyncIOMotorClient
from loguru import logger
from .config import settings

client: AsyncIOMotorClient = None


async def connect_to_mongodb():
    global client
    logger.info("Connecting to MongoDB Atlas...")
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    logger.success("Connected to MongoDB Atlas successfully")


async def close_mongodb_connection():
    global client
    if client:
        client.close()
        logger.info("MongoDB connection closed")


def get_database():
    return client[settings.DATABASE_NAME]
