"""
Supervisor — Central orchestrator.

Enforces execution limits (max 5 iterations).
Routes to the appropriate specialist agent based on classified intent.
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

ROUTE_MAP = {
    "rag": "rag_agent",
    "diagnostic": "diagnostic_agent",
    "pricing": "pricing_agent",
    "general": "rag_agent",
}


class Supervisor:
    """Manages routing and iteration limits."""

    def __init__(self, max_iterations: int = 5):
        self.max_iterations = max_iterations

    def route(self, intent: str, iteration_count: int) -> Dict[str, Any]:
        """
        Decide which specialist agent to invoke.

        Args:
            intent: Classified intent string.
            iteration_count: Current iteration in the pipeline.

        Returns:
            {"route": str, "iteration_count": int}
        """
        if iteration_count >= self.max_iterations:
            logger.warning(f"Max iterations ({self.max_iterations}) reached — forcing summarizer")
            return {"route": "summarizer", "iteration_count": iteration_count + 1}

        route = ROUTE_MAP.get(intent, "rag_agent")
        logger.info(f"Supervisor routing to: {route} (iteration {iteration_count + 1})")

        return {"route": route, "iteration_count": iteration_count + 1}
