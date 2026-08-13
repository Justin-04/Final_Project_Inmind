"""
RAG Agent — Queries MCP server for DJI manual vector search.

Calls: POST http://mcp-server:8002/api/v1/call_tool
Tool: query_dji_manual_vector_db
"""

import os
import logging
from typing import Dict, Any, List

import httpx

logger = logging.getLogger(__name__)

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8002")


class RAGAgent:
    """Fetches relevant manual chunks from the MCP server."""

    def __init__(self, mcp_url: str = None):
        self.mcp_url = mcp_url or MCP_SERVER_URL
        self.timeout = 30

    def execute(self, query: str, conversation_history: List[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Query the vector database for relevant DJI manual content.

        Enriches short queries with conversation context for better retrieval.

        Args:
            query: User's question.
            conversation_history: Last N messages for context.

        Returns:
            {"chunks": list, "query": str} or {"chunks": [], "error": str}
        """
        # Enrich short/ambiguous queries with conversation context
        search_query = self._enrich_query(query, conversation_history)

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    f"{self.mcp_url}/api/v1/call_tool",
                    json={
                        "tool_name": "query_dji_manual_vector_db",
                        "arguments": {
                            "query": search_query,
                            "top_k": 5,
                        },
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            if data.get("status") == "success":
                chunks = data["output"]
                logger.info(f"RAG retrieved {len(chunks)} chunks")
                return {"chunks": chunks, "query": search_query}
            else:
                error = data.get("error", "Unknown MCP error")
                logger.error(f"RAG MCP error: {error}")
                return {"chunks": [], "error": error}

        except httpx.TimeoutException:
            logger.error("RAG agent timeout")
            return {"chunks": [], "error": "MCP server timeout"}
        except Exception as e:
            logger.error(f"RAG agent error: {e}")
            return {"chunks": [], "error": str(e)}

    def _enrich_query(self, query: str, history: List[Dict[str, str]] = None) -> str:
        """Add context from history if query is short/ambiguous."""
        if not history or len(query.split()) >= 6:
            return query

        # Pull recent context to resolve pronouns ("it", "that drone", "its weight")
        recent_content = " ".join(
            m["content"] for m in history[-2:] if m.get("role") in ("user", "assistant")
        )

        # Only prepend if it adds meaningful context
        if recent_content and len(recent_content) < 300:
            return f"{recent_content} {query}"

        return query
