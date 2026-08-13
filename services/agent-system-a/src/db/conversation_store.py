"""
MongoDB Conversation Store.

Persists conversations to MongoDB Atlas.
Provides last N messages for context window.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger(__name__)


class ConversationStore:
    """Async MongoDB conversation persistence."""

    def __init__(self, mongodb_uri: str, db_name: str = "dji_rag"):
        self.client = AsyncIOMotorClient(mongodb_uri)
        self.db = self.client[db_name]
        self.conversations = self.db["conversations"]
        logger.info("MongoDB ConversationStore initialized")

    async def get_or_create_conversation(self, conversation_id: Optional[str], user_id: str) -> str:
        """Get existing conversation or create a new one."""
        if conversation_id:
            doc = await self.conversations.find_one({"conversation_id": conversation_id})
            if doc:
                return conversation_id

        # Create new
        conversation_id = str(uuid.uuid4())
        await self.conversations.insert_one({
            "conversation_id": conversation_id,
            "user_id": user_id,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "messages": [],
        })
        logger.info(f"Created conversation: {conversation_id}")
        return conversation_id

    async def add_message(self, conversation_id: str, role: str, content: str):
        """Append a message to conversation."""
        await self.conversations.update_one(
            {"conversation_id": conversation_id},
            {
                "$push": {"messages": {
                    "role": role,
                    "content": content,
                    "timestamp": datetime.now(timezone.utc),
                }},
                "$set": {"updated_at": datetime.now(timezone.utc)},
            },
        )

    async def get_recent_messages(self, conversation_id: str, limit: int = 4) -> List[Dict[str, str]]:
        """Get last N messages for context window."""
        doc = await self.conversations.find_one(
            {"conversation_id": conversation_id},
            {"messages": {"$slice": -limit}},
        )
        if doc and doc.get("messages"):
            return [{"role": m["role"], "content": m["content"]} for m in doc["messages"]]
        return []

    async def get_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Get full conversation."""
        doc = await self.conversations.find_one(
            {"conversation_id": conversation_id},
            {"_id": 0},
        )
        return doc

    async def list_conversations(self, user_id: str, limit: int = 20) -> List[Dict]:
        """List user's conversations."""
        cursor = self.conversations.find(
            {"user_id": user_id},
            {"_id": 0, "conversation_id": 1, "created_at": 1, "updated_at": 1},
        ).sort("updated_at", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation."""
        result = await self.conversations.delete_one({"conversation_id": conversation_id})
        return result.deleted_count > 0
