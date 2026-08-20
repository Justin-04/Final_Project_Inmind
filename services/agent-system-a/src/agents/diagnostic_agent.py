"""
Diagnostic Agent — LLM-powered error resolution agent.

Uses gpt-4o-mini to:
1. Analyze the query and extract error codes/symptoms
2. Decide whether to look up codes, search manuals, or both
3. Execute the appropriate MCP tool calls
"""

import os
import json
import logging
from typing import Dict, Any, List

import httpx
from openai import OpenAI

from middleware.circuit_breaker import CircuitBreakerOpen
# Import shared MCP circuit breaker from rag_agent
from agents.rag_agent import mcp_circuit_breaker

logger = logging.getLogger(__name__)

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8002")

DIAGNOSTIC_PROMPT = """You are a diagnostic agent for DJI drone troubleshooting.
Analyze the user's problem and decide what actions to take.

Available tools:
1. "lookup_error_code": Look up a specific error code (e.g., E001, E003)
2. "search_manual": Search the manual for troubleshooting steps

Given the query, respond with ONLY a JSON object:
{
  "actions": [
    {"tool": "lookup_error_code", "error_code": "E001"},
    {"tool": "search_manual", "query": "compass calibration troubleshooting"}
  ],
  "reasoning": "why these actions"
}

RULES:
- If a specific error code is mentioned (E001, E003, etc.), ALWAYS look it up
- Also search the manual for related troubleshooting context
- If no specific code is mentioned, just search the manual for the symptoms described
- Extract error codes from various formats: E001, error 001, code E001, etc."""


class DiagnosticAgent:
    """LLM-powered diagnostic and troubleshooting agent."""

    def __init__(self, mcp_url: str = None):
        self.mcp_url = mcp_url or MCP_SERVER_URL
        self.timeout = 120  # Increased for slower cloud environments
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def execute(self, query: str, conversation_history: List[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        LLM analyzes the diagnostic query and executes appropriate tool calls.

        Args:
            query: User's diagnostic question.
            conversation_history: Last N messages.

        Returns:
            {"error_codes": list, "rag_chunks": list}
        """
        # Step 1: LLM plans diagnostic actions
        actions = self._plan_actions(query, conversation_history)

        # Step 2: Execute actions
        error_results = []
        rag_chunks = []

        for action in actions:
            if action.get("tool") == "lookup_error_code":
                code = action.get("error_code", "")
                if code:
                    result = self._lookup_code(code)
                    if result:
                        error_results.append(result)

            elif action.get("tool") == "search_manual":
                search_query = action.get("query", query)
                chunks = self._search_manual(search_query)
                rag_chunks.extend(chunks)

        logger.info(f"Diagnostic agent: {len(error_results)} codes, {len(rag_chunks)} manual chunks")
        return {"error_codes": error_results, "rag_chunks": rag_chunks}

    def _plan_actions(self, query: str, history: List[Dict[str, str]] = None) -> List[Dict]:
        """Use LLM to decide diagnostic actions."""
        history_text = ""
        if history:
            history_text = "\n".join(f"{m['role']}: {m['content']}" for m in history[-3:])

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": DIAGNOSTIC_PROMPT},
                    {"role": "user", "content": f"Context:\n{history_text}\n\nProblem: {query}"},
                ],
                temperature=0.0,
                max_tokens=200,
            )

            text = response.choices[0].message.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            result = json.loads(text)

            actions = result.get("actions", [])
            reasoning = result.get("reasoning", "")
            logger.info(f"Diagnostic planner: {len(actions)} actions — {reasoning}")

            return actions if actions else [{"tool": "search_manual", "query": query}]

        except Exception as e:
            logger.warning(f"Diagnostic planner error: {e} — searching manual directly")
            return [{"tool": "search_manual", "query": query}]

    def _lookup_code(self, error_code: str) -> Dict[str, Any]:
        """Call MCP server to look up an error code (protected by circuit breaker)."""
        try:
            def _do_lookup():
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(
                        f"{self.mcp_url}/api/v1/call_tool",
                        json={
                            "tool_name": "lookup_dji_error_code_db",
                            "arguments": {"error_code": error_code},
                        },
                    )
                    resp.raise_for_status()
                    return resp.json()

            data = mcp_circuit_breaker.call(_do_lookup)

            if data.get("status") == "success":
                return data["output"]
            return None

        except CircuitBreakerOpen as e:
            logger.warning(f"Error code lookup blocked: {e}")
            return None
        except Exception as e:
            logger.warning(f"Error code lookup failed: {e}")
            return None

    def _search_manual(self, query: str) -> List[Dict[str, Any]]:
        """Search manual for troubleshooting context (protected by circuit breaker)."""
        try:
            def _do_search():
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(
                        f"{self.mcp_url}/api/v1/call_tool",
                        json={
                            "tool_name": "query_dji_manual_vector_db",
                            "arguments": {"query": query, "top_k": 3},
                        },
                    )
                    resp.raise_for_status()
                    return resp.json()

            data = mcp_circuit_breaker.call(_do_search)

            if data.get("status") == "success":
                return data["output"]
            return []

        except CircuitBreakerOpen as e:
            logger.warning(f"Diagnostic manual search blocked: {e}")
            return []
        except Exception as e:
            logger.warning(f"Diagnostic manual search failed: {e}")
            return []
