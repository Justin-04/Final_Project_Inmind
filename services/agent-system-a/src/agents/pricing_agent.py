"""
Pricing Agent — LLM-powered agent that calls agent-system-b over HTTP A2A.

Uses gpt-4o-mini to:
1. Analyze the pricing query
2. Extract drone model(s) from query + conversation context
3. Decide if single or multi-model comparison is needed
4. Call agent-system-b with the correct parameters
"""

import os
import json
import logging
from typing import Dict, Any, List

import httpx
from openai import OpenAI

from middleware.circuit_breaker import CircuitBreaker, CircuitBreakerOpen

logger = logging.getLogger(__name__)

AGENT_B_URL = os.getenv("AGENT_B_URL", "http://localhost:8001")

# Circuit breaker for agent-system-b calls
agent_b_circuit_breaker = CircuitBreaker("agent-system-b", failure_threshold=3, recovery_timeout=30)

PLANNER_PROMPT = """You are a pricing query analyzer for DJI drones.
Given the user's query and conversation history, extract the drone model(s) to look up pricing for.

RULES:
- Extract the exact drone model name(s) mentioned
- If the user says "it" or "that drone", resolve from conversation history
- If multiple models are mentioned (comparison), return all of them
- Return the model name as the user would say it (e.g., "mini_4_pro", "air_3", "avata_2", "neo")
- If no specific model is found, use the query itself as the search term

Respond with ONLY a JSON object:
{
  "models": ["model_1", "model_2"],
  "query": "the user's pricing question",
  "reasoning": "why these models"
}

Examples:
- "How much is the Mini 4 Pro?" → {"models": ["mini_4_pro"], "query": "DJI Mini 4 Pro price", "reasoning": "single model pricing"}
- "Compare prices of Air 3 and Mavic 3" → {"models": ["air_3", "mavic_3_pro"], "query": "price comparison", "reasoning": "multi-model comparison"}
- "What about its price?" (history mentions Neo) → {"models": ["neo"], "query": "DJI Neo price", "reasoning": "resolved from history"}
- "How much is the DJI Avata 2?" → {"models": ["avata_2"], "query": "DJI Avata 2 price", "reasoning": "single model pricing"}"""


class PricingAgent:
    """LLM-powered pricing agent that calls agent-system-b via HTTP A2A."""

    def __init__(self, agent_b_url: str = None):
        self.agent_b_url = agent_b_url or AGENT_B_URL
        self.timeout = 60
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def execute(self, query: str, conversation_history: List[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        LLM analyzes the query, extracts models, calls system-b.

        Args:
            query: User's pricing question.
            conversation_history: Last N messages for context.

        Returns:
            dict: Pricing response(s) from agent-system-b.
        """
        # Step 1: LLM extracts model(s) from query
        plan = self._plan_pricing(query, conversation_history)
        models = plan.get("models", [])

        if not models:
            models = [query[:50]]  # Fallback: pass raw query

        # Step 2: Call system-b for each model
        if len(models) >= 2:
            # Multi-model comparison
            all_results = []
            for model in models:
                result = self._call_system_b(model, query)
                all_results.append(result)

            merged_vendors = []
            for r in all_results:
                for v in r.get("vendors", []):
                    v["drone_model"] = r.get("display_name", r.get("drone_model", ""))
                    merged_vendors.append(v)

            logger.info(f"Pricing agent: multi-model {models} → {len(merged_vendors)} vendors")
            return {
                "vendors": merged_vendors,
                "multi_model": True,
                "models_compared": [r.get("display_name", "") for r in all_results],
                "summary_notes": f"Pricing comparison for: {', '.join(models)}",
            }
        else:
            # Single model
            return self._call_system_b(models[0], query)

    def _plan_pricing(self, query: str, history: List[Dict[str, str]] = None) -> Dict:
        """Use LLM to extract drone model(s) from the query."""
        history_text = ""
        if history:
            history_text = "\n".join(f"{m['role']}: {m['content']}" for m in history[-3:])

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": PLANNER_PROMPT},
                    {"role": "user", "content": f"Conversation:\n{history_text}\n\nQuery: {query}"},
                ],
                temperature=0.0,
                max_tokens=150,
            )

            text = response.choices[0].message.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            result = json.loads(text)

            logger.info(f"Pricing planner: models={result.get('models')} — {result.get('reasoning')}")
            return result

        except Exception as e:
            logger.warning(f"Pricing planner error: {e}")
            return {"models": [], "query": query}

    def _call_system_b(self, drone_model: str, query: str) -> Dict[str, Any]:
        """Make a single HTTP call to agent-system-b (protected by circuit breaker)."""
        try:
            def _do_call():
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
                    return resp.json()

            data = agent_b_circuit_breaker.call(_do_call)

            logger.info(f"Pricing: got {len(data.get('vendors', []))} vendors for '{drone_model}'")
            return data

        except CircuitBreakerOpen as e:
            logger.warning(f"Pricing call blocked: {e}")
            return {
                "error": "Pricing service temporarily unavailable. Please try again shortly.",
                "vendors": [],
                "drone_model": drone_model,
            }
        except httpx.TimeoutException:
            logger.error(f"Pricing timeout for '{drone_model}'")
            return {"error": "Pricing service timeout", "vendors": [], "drone_model": drone_model}
        except Exception as e:
            logger.error(f"Pricing error for '{drone_model}': {e}")
            return {"error": str(e), "vendors": [], "drone_model": drone_model}
