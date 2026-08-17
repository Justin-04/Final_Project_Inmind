"""
Supervisor — LLM-powered central orchestrator.

Uses gpt-4o-mini to analyze the query and decide which specialist agent to route to.
Enforces max 5 iterations.
"""

import os
import json
import logging
from typing import Dict, Any

from openai import OpenAI

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a routing supervisor for a DJI drone support system. 
Analyze the user's query and decide which specialist agent should handle it.

Available agents:
- "rag_agent": For technical questions about drone specs, features, how-to guides, manual content, comparisons between drones
- "diagnostic_agent": For error codes, LED patterns, calibration failures, troubleshooting hardware problems
- "pricing_agent": For pricing, purchasing, vendor comparisons, deals, stock availability, where to buy
- "general": For greetings, thank you messages, chitchat, "who are you", or anything that is NOT a DJI drone question

RULES:
- If the query is a greeting (hello, hi, hey), thanks, or general chitchat → "general"
- If the query asks about you/the system (who are you, what can you do) → "general"
- Only use rag/diagnostic/pricing for actual DJI drone questions

Respond with ONLY a JSON object:
{"route": "rag_agent" | "diagnostic_agent" | "pricing_agent" | "general", "reasoning": "one sentence why"}"""


class Supervisor:
    """LLM-powered routing supervisor."""

    def __init__(self, max_iterations: int = 5):
        self.max_iterations = max_iterations
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def route(self, query: str, conversation_history: list, iteration_count: int) -> Dict[str, Any]:
        """
        Use LLM to decide which agent should handle this query.

        Args:
            query: User's question.
            conversation_history: Recent messages for context.
            iteration_count: Current iteration.

        Returns:
            {"route": str, "iteration_count": int}
        """
        if iteration_count >= self.max_iterations:
            logger.warning(f"Max iterations ({self.max_iterations}) reached")
            return {"route": "summarizer", "iteration_count": iteration_count + 1}

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
                max_tokens=80,
            )

            text = response.choices[0].message.content.strip()
            result = json.loads(text)
            route = result.get("route", "rag_agent")
            reasoning = result.get("reasoning", "")

            # Validate route
            valid_routes = ["rag_agent", "diagnostic_agent", "pricing_agent", "general"]
            if route not in valid_routes:
                route = "rag_agent"

            # "general" maps to "summarizer" in the graph (skip specialists)
            if route == "general":
                route = "summarizer"

            logger.info(f"Supervisor: {route} — {reasoning}")
            return {"route": route, "iteration_count": iteration_count + 1}

        except Exception as e:
            logger.warning(f"Supervisor LLM error: {e} — defaulting to rag_agent")
            return {"route": "rag_agent", "iteration_count": iteration_count + 1}
