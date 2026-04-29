"""
database.py — MongoDB Atlas connection using Motor (async)
"""
from motor.motor_asyncio import AsyncIOMotorClient
from loguru import logger
from .config import settings

# Global database client
client: AsyncIOMotorClient = None


async def connect_to_mongodb():
    """Connect to MongoDB Atlas on startup."""
    global client
    logger.info("Connecting to MongoDB Atlas...")
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    logger.success("Connected to MongoDB Atlas successfully")


async def close_mongodb_connection():
    """Close MongoDB connection on shutdown."""
    global client
    if client:
        client.close()
        logger.info("MongoDB connection closed")


def get_database():
    """Return the database instance."""
    return client[settings.DATABASE_NAME]