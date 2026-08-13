"""
Pricing Agent — Calls agent-system-b over HTTP A2A.

Sends: POST http://agent-system-b:8001/v1/pricing
Returns structured vendor pricing data.

Does NOT hardcode drone models — extracts whatever model
the user mentions and passes it to system-b.
"""

import os
import re
import logging
from typing import Dict, Any, List

import httpx

logger = logging.getLogger(__name__)

AGENT_B_URL = os.getenv("AGENT_B_URL", "http://localhost:8001")


class PricingAgent:
    """Calls agent-system-b for vendor pricing via HTTP A2A."""

    def __init__(self, agent_b_url: str = None):
        self.agent_b_url = agent_b_url or AGENT_B_URL
        self.timeout = 60  # Agent B takes time (LLM + web search)

    def execute(self, query: str, conversation_history: List[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Call agent-system-b for pricing.

        Extracts the drone model from the query/history dynamically
        (no hardcoded list — supports any DJI model).

        Args:
            query: User's pricing question.
            conversation_history: Last N messages for model extraction.

        Returns:
            dict: Pricing response from agent-system-b or error.
        """
        drone_model = self._extract_drone_model(query, conversation_history)

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    f"{self.agent_b_url}/v1/pricing",
                    json={
                        "drone_model": drone_model,
                        "query": query,
                        "currency": "USD",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            logger.info(f"Pricing agent got {len(data.get('vendors', []))} vendors for '{drone_model}'")
            return data

        except httpx.TimeoutException:
            logger.error("Pricing agent timeout (agent-system-b)")
            return {"error": "Pricing service timeout", "vendors": []}
        except Exception as e:
            logger.error(f"Pricing agent error: {e}")
            return {"error": str(e), "vendors": []}

    def _extract_drone_model(self, query: str, history: List[Dict[str, str]] = None) -> str:
        """
        Extract drone model from query or conversation history.

        Dynamically finds DJI model names — not limited to a hardcoded list.
        Looks for patterns like "DJI <model name>" or known model keywords.
        """
        # Combine query + recent history
        text = query
        if history:
            text += " " + " ".join(m.get("content", "") for m in history[-4:])
        text_lower = text.lower()

        # Pattern: "dji <word(s)> <number/pro/etc>"
        # Matches: DJI Mini 4 Pro, DJI Air 3, DJI Mavic 3 Pro, DJI Neo, DJI Avata 2, etc.
        dji_pattern = re.search(
            r'dji\s+([\w\s]+?)(?:\s+(?:drone|price|cost|buy|how|what|is|the|for|in|at)|\?|$)',
            text_lower,
        )
        if dji_pattern:
            model = dji_pattern.group(1).strip()
            # Clean trailing common words
            model = re.sub(r'\s+(price|cost|buy|how|what|is|much|the)$', '', model)
            if model:
                return model.replace(" ", "_")

        # Fallback: look for known patterns without "DJI" prefix
        known_patterns = [
            r'(mini\s*4\s*pro)',
            r'(mini\s*3\s*pro)',
            r'(mini\s*3)',
            r'(mini\s*2)',
            r'(air\s*3)',
            r'(air\s*2s?)',
            r'(mavic\s*3\s*pro)',
            r'(mavic\s*3\s*classic)',
            r'(mavic\s*3)',
            r'(avata\s*2?)',
            r'(neo)',
            r'(phantom\s*\d)',
            r'(inspire\s*\d)',
        ]

        for pattern in known_patterns:
            match = re.search(pattern, text_lower)
            if match:
                return match.group(1).strip().replace(" ", "_")

        # Last resort: just pass the query as-is (system-b's LLM will figure it out)
        return query[:50].replace(" ", "_")
