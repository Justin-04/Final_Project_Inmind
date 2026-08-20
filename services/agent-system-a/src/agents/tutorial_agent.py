"""
Tutorial Agent — LLM-powered YouTube tutorial search.

Uses gpt-4o-mini to:
1. Analyze the user's query and conversation context
2. Generate an optimized YouTube search query
3. Call agent-system-b's /v1/tutorials endpoint
"""

import os
import json
import logging
from typing import Dict, Any, List

import httpx
from openai import OpenAI

from middleware.circuit_breaker import CircuitBreakerOpen
from agents.pricing_agent import agent_b_circuit_breaker

logger = logging.getLogger(__name__)

AGENT_B_URL = os.getenv("AGENT_B_URL", "http://localhost:8001")

PLANNER_PROMPT = """You are a YouTube search query optimizer for DJI drone tutorials.
Given the user's question, generate the best YouTube search query to find a helpful tutorial video.

RULES:
- Include the specific drone model if mentioned
- Add "tutorial", "how to", or "guide" if not already present
- Keep it concise (5-8 words max)
- Optimize for YouTube's search algorithm (use popular search terms)
- If the query is vague, make it specific to DJI drones

Respond with ONLY a JSON object:
{"search_query": "optimized youtube search query", "reasoning": "why this query"}

Examples:
- "how do I fly the Air 3?" → {"search_query": "DJI Air 3 first flight tutorial beginner", "reasoning": "added model name and beginner keyword for better results"}
- "setup guide" → {"search_query": "DJI drone setup guide unboxing first time", "reasoning": "generic setup, added unboxing keyword popular on YouTube"}
- "how to calibrate compass on Mini 4 Pro" → {"search_query": "DJI Mini 4 Pro compass calibration tutorial", "reasoning": "specific model and action"}"""


class TutorialAgent:
    """LLM-powered YouTube tutorial search agent."""

    def __init__(self, agent_b_url: str = None):
        self.agent_b_url = agent_b_url or AGENT_B_URL
        self.timeout = 30
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def execute(self, query: str, conversation_history: List[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        LLM optimizes the search query, then calls agent-system-b for YouTube results.

        Args:
            query: User's tutorial request.
            conversation_history: Last N messages for context.

        Returns:
            {"videos": list, "query": str, "search_query": str}
        """
        # Step 1: LLM optimizes the YouTube search query
        search_query = self._plan_search(query, conversation_history)

        # Step 2: Call agent-system-b
        videos = self._search_tutorials(search_query)

        logger.info(f"Tutorial agent: '{query}' → search: '{search_query}' → {len(videos)} videos")
        return {"videos": videos, "query": query, "search_query": search_query}

    def _plan_search(self, query: str, history: List[Dict[str, str]] = None) -> str:
        """Use LLM to generate an optimized YouTube search query."""
        history_text = ""
        if history:
            history_text = "\n".join(f"{m['role']}: {m['content']}" for m in history[-2:])

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": PLANNER_PROMPT},
                    {"role": "user", "content": f"Context:\n{history_text}\n\nUser request: {query}"},
                ],
                temperature=0.2,
                max_tokens=100,
            )

            text = response.choices[0].message.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            result = json.loads(text)

            search_query = result.get("search_query", query)
            reasoning = result.get("reasoning", "")
            logger.info(f"Tutorial planner: '{search_query}' — {reasoning}")
            print(f"   [Tutorial] Optimized search: '{search_query}'")

            return search_query

        except Exception as e:
            logger.warning(f"Tutorial planner error: {e} — using raw query")
            return query

    def _search_tutorials(self, search_query: str) -> List[Dict[str, Any]]:
        """Call agent-system-b's tutorial endpoint (protected by circuit breaker)."""
        try:
            def _do_call():
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(
                        f"{self.agent_b_url}/v1/tutorials",
                        json={"query": search_query, "max_results": 5},
                    )
                    resp.raise_for_status()
                    return resp.json()

            data = agent_b_circuit_breaker.call(_do_call)
            return data.get("videos", [])

        except CircuitBreakerOpen as e:
            logger.warning(f"Tutorial search blocked: {e}")
            return []
        except Exception as e:
            logger.error(f"Tutorial search error: {e}")
            return []
