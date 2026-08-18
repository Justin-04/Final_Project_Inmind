"""
Agent State for agent-system-a LangGraph pipeline.
"""

from typing import TypedDict, List, Dict, Any, Optional


class AgentState(TypedDict):
    """Shared state flowing through the LangGraph pipeline."""

    # --- Input ---
    query: str
    user_id: str
    conversation_id: str
    conversation_history: List[Dict[str, str]]  # Last N messages for context

    # --- Intent Classification ---
    intent: str            # "rag", "diagnostic", "pricing", "general"
    confidence: float

    # --- Guardrails ---
    input_safe: bool
    guardrail_message: Optional[str]

    # --- Supervisor ---
    iteration_count: int
    max_iterations: int
    route: str  # Primary route (first in routes list)
    routes: List[str]  # All routes to execute (multi-route support)

    # --- Agent Results ---
    rag_result: Optional[Dict[str, Any]]
    diagnostic_result: Optional[Dict[str, Any]]
    pricing_result: Optional[Dict[str, Any]]

    # --- Final Output ---
    final_response: str
