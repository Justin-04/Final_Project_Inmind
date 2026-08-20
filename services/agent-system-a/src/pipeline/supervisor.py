"""
Supervisor — LLM-powered central orchestrator.

Uses gpt-4o-mini to analyze the query and decide which specialist agent(s) to route to.
Supports multi-route for queries spanning multiple domains.
Enforces max 5 iterations.
"""

import os
import json
import logging
from typing import Dict, Any

from openai import OpenAI

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a routing supervisor for a DJI drone support system. 
Analyze the user's query and decide which specialist agent(s) should handle it.

Available agents:
- "rag_agent": For technical questions about drone specs, features, how-to guides, manual content, comparisons between drones
- "diagnostic_agent": For error codes, LED patterns, calibration failures, troubleshooting hardware problems
- "pricing_agent": For pricing, purchasing, vendor comparisons, deals, stock availability, where to buy
- "tutorial_agent": For requests about tutorials, how-to videos, learning to fly, setup guides, YouTube content
- "general": For greetings, thank you messages, chitchat, "who are you", or anything that is NOT a DJI drone question

RULES:
- If the query is a greeting (hello, hi, hey), thanks, or general chitchat → ["general"]
- If the query asks about you/the system (who are you, what can you do) → ["general"]
- If the query spans MULTIPLE domains (e.g. "what is the weight AND error code E001"), return MULTIPLE routes
- For single-domain questions, return a single route in the array
- Only use rag/diagnostic/pricing for actual DJI drone questions

Respond with ONLY a JSON object:
{"routes": ["rag_agent", "diagnostic_agent"] | ["pricing_agent"] | ["general"], "reasoning": "one sentence why"}

Examples:
- "What is the max speed?" → {"routes": ["rag_agent"], "reasoning": "specs question"}
- "What is the weight and error code E001?" → {"routes": ["rag_agent", "diagnostic_agent"], "reasoning": "specs + error code"}
- "Compare prices and specs of Air 3" → {"routes": ["rag_agent", "pricing_agent"], "reasoning": "specs + pricing"}
- "Hello" → {"routes": ["general"], "reasoning": "greeting"}"""


class Supervisor:
    """LLM-powered routing supervisor with multi-route support."""

    def __init__(self, max_iterations: int = 5):
        self.max_iterations = max_iterations
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def route(self, query: str, conversation_history: list, iteration_count: int) -> Dict[str, Any]:
        """
        Use LLM to decide which agent(s) should handle this query.

        Returns:
            {"route": str, "routes": list, "iteration_count": int}
            - "route" is the primary route (first in list) for backward compat
            - "routes" is the full list of agents to call
        """
        if iteration_count >= self.max_iterations:
            logger.warning(f"Max iterations ({self.max_iterations}) reached")
            return {"route": "summarizer", "routes": ["summarizer"], "iteration_count": iteration_count + 1}

        # Build context from history
        history_text = ""
        if conversation_history:
            history_text = "\n".join(
                f"{m['role']}: {m['content']}" for m in conversation_history[-3:]
            )

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Conversation context:\n{history_text}\n\nCurrent query: {query}"},
                ],
                temperature=0.0,
                max_tokens=100,
            )

            text = response.choices[0].message.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            result = json.loads(text)

            # Support both "routes" (new) and "route" (old format)
            routes = result.get("routes", [result.get("route", "rag_agent")])
            if isinstance(routes, str):
                routes = [routes]

            reasoning = result.get("reasoning", "")

            # Validate routes
            valid_routes = ["rag_agent", "diagnostic_agent", "pricing_agent", "tutorial_agent", "general"]
            routes = [r for r in routes if r in valid_routes] or ["rag_agent"]

            # "general" maps to "summarizer"
            routes = ["summarizer" if r == "general" else r for r in routes]

            primary_route = routes[0]

            logger.info(f"Supervisor: {routes} — {reasoning}")
            return {"route": primary_route, "routes": routes, "iteration_count": iteration_count + 1}

        except Exception as e:
            logger.warning(f"Supervisor LLM error: {e} — defaulting to rag_agent")
            return {"route": "rag_agent", "routes": ["rag_agent"], "iteration_count": iteration_count + 1}
