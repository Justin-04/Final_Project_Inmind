"""
Diagnostic Agent — Looks up error codes and troubleshooting info.

Calls MCP server for:
1. lookup_dji_error_code_db — exact error code match
2. query_dji_manual_vector_db — related manual context
"""

import os
import re
import logging
from typing import Dict, Any, List

import httpx

logger = logging.getLogger(__name__)

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8002")


class DiagnosticAgent:
    """Resolves DJI error codes and fetches troubleshooting context."""

    def __init__(self, mcp_url: str = None):
        self.mcp_url = mcp_url or MCP_SERVER_URL
        self.timeout = 20

    def execute(self, query: str, conversation_history: List[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Look up error codes and fetch related diagnostic context.

        Args:
            query: User's diagnostic question.
            conversation_history: Last N messages.

        Returns:
            {"error_codes": list, "rag_chunks": list}
        """
        # Extract error codes from query + history
        full_text = query
        if conversation_history:
            full_text += " " + " ".join(m.get("content", "") for m in conversation_history[-2:])

        codes = self._extract_error_codes(full_text)
        error_results = []
        rag_chunks = []

        # Look up each error code
        for code in codes:
            result = self._lookup_code(code)
            if result:
                error_results.append(result)

        # Also fetch related manual content via RAG
        rag_chunks = self._search_manual(query)

        logger.info(f"Diagnostic: {len(error_results)} codes, {len(rag_chunks)} chunks")
        return {"error_codes": error_results, "rag_chunks": rag_chunks}

    def _extract_error_codes(self, text: str) -> List[str]:
        """Extract error code patterns from text."""
        patterns = [
            r'\bE\d{3,4}\b',          # E001, E0012
            r'\b[A-Z]+_[A-Z]+\b',     # COMPASS_ERR
            r'\berror\s*\d+\b',        # error 001
        ]
        codes = []
        for pattern in patterns:
            codes.extend(re.findall(pattern, text, re.IGNORECASE))
        return list(set(codes))

    def _lookup_code(self, error_code: str) -> Dict[str, Any]:
        """Call MCP server to look up a single error code."""
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    f"{self.mcp_url}/api/v1/call_tool",
                    json={
                        "tool_name": "lookup_dji_error_code_db",
                        "arguments": {"error_code": error_code},
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            if data.get("status") == "success":
                return data["output"]
            return None

        except Exception as e:
            logger.warning(f"Error code lookup failed for {error_code}: {e}")
            return {"code": error_code, "found": False, "error": str(e)}

    def _search_manual(self, query: str) -> List[Dict[str, Any]]:
        """Fetch related manual content for diagnostic context."""
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    f"{self.mcp_url}/api/v1/call_tool",
                    json={
                        "tool_name": "query_dji_manual_vector_db",
                        "arguments": {"query": query, "top_k": 3},
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            if data.get("status") == "success":
                return data["output"]
            return []

        except Exception as e:
            logger.warning(f"Diagnostic RAG search failed: {e}")
            return []
