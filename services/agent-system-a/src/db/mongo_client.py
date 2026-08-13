"""
MongoDB Atlas Client

Connects to the hosted MongoDB cluster using the URI from environment.
"""

import os
import logging
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger(__name__)

_client: AsyncIOMotorClient = None


def get_client() -> AsyncIOMotorClient:
    """Get or create the MongoDB async client (singleton)."""
    global _client
    if _client is None:
        uri = os.getenv("MONGODB_URI")
        if not uri:
            raise ValueError("MONGODB_URI environment variable is not set")
        _client = AsyncIOMotorClient(uri)
        logger.info("Connected to MongoDB Atlas cluster")
    return _client


def get_db(db_name: str = "dji_rag"):
    """
    Get a database reference.

    Args:
        db_name: Database name (default: dji_rag)

    Returns:
        AsyncIOMotorDatabase
    """
    return get_client()[db_name]


async def close_client():
    """Close the MongoDB connection (call on app shutdown)."""
    global _client
    if _client:
        _client.close()
        _client = None
        logger.info("MongoDB connection closed")
