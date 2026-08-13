"""
Agent State Definition for agent-system-b
"""

from typing import TypedDict, List, Dict, Any, Optional


class AgentState(TypedDict):
    """Shared state for the agent-system-b LLM agent pipeline."""

    # --- Input Fields ---
    drone_model: str
    part_category: Optional[str]
    search_query: Optional[str]
    part_id: Optional[str]
    currency: str

    # --- Agent Results ---
    vendors: List[Dict[str, Any]]
    confidence: float
    final_response: Dict[str, Any]
    errors: List[str]
