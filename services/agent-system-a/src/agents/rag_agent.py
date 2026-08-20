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

from middleware.circuit_breaker import CircuitBreaker, CircuitBreakerOpen

logger = logging.getLogger(__name__)

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8002")

# Circuit breaker for MCP server calls (shared across RAG + Diagnostic agents)
mcp_circuit_breaker = CircuitBreaker("mcp-server", failure_threshold=3, recovery_timeout=30)

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
    """LLM-powered retrieval agent that plans and executes searches with query rewriting on failure."""

    def __init__(self, mcp_url: str = None):
        self.mcp_url = mcp_url or MCP_SERVER_URL
        self.timeout = 120  # Increased for slower cloud environments
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def execute(self, query: str, conversation_history: List[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        LLM plans the search strategy, then executes it.
        If results are weak/empty, rewrites the query and retries once.

        1. LLM analyzes query → produces search plan
        2. Execute each search in the plan
        3. If chunks are empty or weak → rewrite query and retry
        4. Return merged chunks

        Args:
            query: User's question.
            conversation_history: Last N messages for context.

        Returns:
            {"chunks": list, "query": str}
        """
        # Step 1: LLM plans the search strategy
        search_plan = self._plan_search(query, conversation_history)

        # Step 2: Execute searches
        all_chunks = self._execute_searches(search_plan, query)

        # Step 3: Evaluate — if no chunks found, rewrite and retry
        if not all_chunks:
            logger.info("RAG agent: 0 chunks on first attempt — rewriting query...")
            print("   [RAG] No results — attempting query rewrite...")

            rewritten_plan = self._rewrite_query(query, search_plan)
            all_chunks = self._execute_searches(rewritten_plan, query)

            if all_chunks:
                logger.info(f"RAG agent: query rewrite succeeded — {len(all_chunks)} chunks")
                print(f"   [RAG] Rewrite succeeded! Got {len(all_chunks)} chunks")
            else:
                logger.info("RAG agent: query rewrite also returned 0 chunks")
                print("   [RAG] Rewrite also failed — no relevant content found")

        else:
            logger.info(f"RAG agent: {len(search_plan)} searches → {len(all_chunks)} chunks")

        return {"chunks": all_chunks, "query": query}

    def _execute_searches(self, search_plan: List[Dict], original_query: str) -> List[Dict[str, Any]]:
        """Execute all searches in the plan and return merged chunks."""
        all_chunks = []
        for search in search_plan:
            chunks = self._search_mcp(
                query=search.get("query", original_query),
                drone_model=search.get("drone_model"),
                top_k=search.get("top_k", 4),
            )
            all_chunks.extend(chunks)
        return all_chunks

    def _rewrite_query(self, original_query: str, failed_plan: List[Dict]) -> List[Dict]:
        """
        LLM rewrites the query when first attempt returns no results.
        Strategies: remove filters, expand acronyms, use synonyms, broaden search.
        """
        failed_queries = [s.get("query", "") for s in failed_plan]
        failed_filters = [s.get("drone_model") for s in failed_plan]

        rewrite_prompt = f"""The following search queries returned NO results from a DJI drone manual vector database:

Queries tried: {failed_queries}
Filters used: {failed_filters}
Original user question: "{original_query}"

The database contains DJI drone user manuals with technical specs, instructions, and troubleshooting.

Rewrite the search to find relevant content. Strategies:
- Remove drone_model filters (search across all manuals)
- Expand acronyms (e.g., "RC-N2" → "remote controller RC-N2")
- Use synonyms or related terms
- Break compound questions into simpler searches
- Use terms likely found in a technical manual

Respond with ONLY a JSON object:
{{"searches": [{{"query": "rewritten query", "drone_model": null, "top_k": 6}}]}}"""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You rewrite failed search queries to improve retrieval from a technical manual database."},
                    {"role": "user", "content": rewrite_prompt},
                ],
                temperature=0.3,
                max_tokens=200,
            )

            text = response.choices[0].message.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            result = json.loads(text)

            searches = result.get("searches", [])
            # Limit to max 3 rewritten queries to control latency
            searches = searches[:3]
            logger.info(f"RAG rewrite: {[s.get('query') for s in searches]}")
            print(f"   [RAG] Rewritten queries: {[s.get('query') for s in searches]}")
            return searches if searches else [{"query": original_query, "drone_model": None, "top_k": 6}]

        except Exception as e:
            logger.warning(f"Query rewrite failed: {e}")
            # Fallback: remove all filters and increase top_k
            return [{"query": original_query, "drone_model": None, "top_k": 6}]

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
        """Execute a single MCP search call (protected by circuit breaker)."""
        arguments = {"query": query, "top_k": top_k}
        if drone_model:
            arguments["drone_model"] = drone_model

        try:
            def _do_search():
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(
                        f"{self.mcp_url}/api/v1/call_tool",
                        json={
                            "tool_name": "query_dji_manual_vector_db",
                            "arguments": arguments,
                        },
                    )
                    resp.raise_for_status()
                    return resp.json()

            data = mcp_circuit_breaker.call(_do_search)

            if data.get("status") == "success":
                return data["output"]
            return []

        except CircuitBreakerOpen as e:
            logger.warning(f"RAG search blocked: {e}")
            return []
        except Exception as e:
            logger.error(f"MCP search error: {e}")
            return []
