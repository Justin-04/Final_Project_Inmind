"""
RAG Agent — LLM-powered retrieval agent.

Uses gpt-4o-mini to:
1. Analyze the query and decide search strategy
2. Detect drone models and determine if multi-search is needed
3. Rewrite the query for better retrieval
4. Call the MCP server with optimized parameters
"""

import os
import json
import logging
from typing import Dict, Any, List

import httpx
from openai import OpenAI

logger = logging.getLogger(__name__)

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8002")

PLANNER_PROMPT = """You are a search planner for a DJI drone manual RAG system.
Given the user's query, plan the retrieval strategy.

You have access to a vector search tool that accepts:
- query: search text
- drone_model: optional filter (MUST use exact names below)
- top_k: number of results (default 4)

AVAILABLE DRONE MODELS (use these exact names for filtering):
- "DJI Mini 4 Pro"
- "DJI Air 3"
- "DJI Neo"
- "DJI Mavic 3 Classic"

RULES:
- If a specific drone model is mentioned, filter by it using the EXACT name from the list above
- "Mavic 3" or "Mavic 3 Pro" → use "DJI Mavic 3 Classic"
- "Mini 4 Pro" → use "DJI Mini 4 Pro"
- "Air 3" → use "DJI Air 3"
- "Neo" → use "DJI Neo"
- If multiple models are mentioned (comparison), plan separate searches for each
- Rewrite the query to match technical manual language (specs, measurements, values)
- For comparisons, use spec-focused queries like "specifications max speed m/s"

Respond with ONLY a JSON object:
{
  "searches": [
    {"query": "rewritten search query", "drone_model": "exact model name or null", "top_k": 4}
  ],
  "reasoning": "why this strategy"
}

Examples:
- "What is the max speed of Air 3?" → {"searches": [{"query": "specifications max horizontal speed m/s", "drone_model": "DJI Air 3", "top_k": 4}]}
- "Compare battery life of Air 3 and Mavic 3" → {"searches": [{"query": "specifications max flight time battery minutes", "drone_model": "DJI Air 3", "top_k": 3}, {"query": "specifications max flight time battery minutes", "drone_model": "DJI Mavic 3 Classic", "top_k": 3}]}
- "How do I calibrate the gimbal?" → {"searches": [{"query": "gimbal calibration procedure steps", "drone_model": null, "top_k": 4}]}"""


class RAGAgent:
    """LLM-powered retrieval agent that plans and executes searches."""

    def __init__(self, mcp_url: str = None):
        self.mcp_url = mcp_url or MCP_SERVER_URL
        self.timeout = 30
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def execute(self, query: str, conversation_history: List[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        LLM plans the search strategy, then executes it.

        1. LLM analyzes query → produces search plan
        2. Execute each search in the plan
        3. Return merged chunks

        Args:
            query: User's question.
            conversation_history: Last N messages for context.

        Returns:
            {"chunks": list, "query": str}
        """
        # Step 1: LLM plans the search strategy
        search_plan = self._plan_search(query, conversation_history)

        # Step 2: Execute searches
        all_chunks = []
        for search in search_plan:
            chunks = self._search_mcp(
                query=search.get("query", query),
                drone_model=search.get("drone_model"),
                top_k=search.get("top_k", 4),
            )
            all_chunks.extend(chunks)

        logger.info(f"RAG agent: {len(search_plan)} searches → {len(all_chunks)} chunks")
        return {"chunks": all_chunks, "query": query}

    def _plan_search(self, query: str, history: List[Dict[str, str]] = None) -> List[Dict]:
        """Use LLM to plan the retrieval strategy."""
        history_text = ""
        if history:
            history_text = "\n".join(f"{m['role']}: {m['content']}" for m in history[-3:])

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": PLANNER_PROMPT},
                    {"role": "user", "content": f"Context:\n{history_text}\n\nQuery: {query}"},
                ],
                temperature=0.0,
                max_tokens=300,
            )

            text = response.choices[0].message.content.strip()
            # Parse JSON (handle markdown fences)
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            result = json.loads(text)

            searches = result.get("searches", [])
            reasoning = result.get("reasoning", "")
            logger.info(f"RAG planner: {len(searches)} searches planned — {reasoning}")

            return searches if searches else [{"query": query, "drone_model": None, "top_k": 4}]

        except Exception as e:
            logger.warning(f"RAG planner error: {e} — using raw query")
            return [{"query": query, "drone_model": None, "top_k": 4}]

    def _search_mcp(self, query: str, drone_model: str = None, top_k: int = 4) -> List[Dict[str, Any]]:
        """Execute a single MCP search call."""
        arguments = {"query": query, "top_k": top_k}
        if drone_model:
            arguments["drone_model"] = drone_model

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    f"{self.mcp_url}/api/v1/call_tool",
                    json={
                        "tool_name": "query_dji_manual_vector_db",
                        "arguments": arguments,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            if data.get("status") == "success":
                return data["output"]
            return []

        except Exception as e:
            logger.error(f"MCP search error: {e}")
            return []
