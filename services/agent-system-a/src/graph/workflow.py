"""
LangGraph Workflow for agent-system-a.

Full pipeline:
  input_guard → classifier → supervisor → [rag/diagnostic/pricing] → summarizer → END
"""

import logging
from langgraph.graph import StateGraph, END
from src.state.agent_state import AgentState
from src.graph.nodes import (
    input_guard_node,
    classifier_node,
    supervisor_node,
    rag_agent_node,
    diagnostic_agent_node,
    pricing_agent_node,
    summarizer_node,
)

logger = logging.getLogger(__name__)


def route_after_guard(state: AgentState) -> str:
    """If input is unsafe, skip to END with blocked message."""
    if not state.get("input_safe", True):
        return "blocked"
    return "classify"


def route_after_supervisor(state: AgentState) -> str:
    """Route to the correct specialist agent."""
    route = state.get("route", "rag_agent")
    if route == "summarizer":
        return "summarizer"
    return route


def build_graph():
    """
    Build the full agent-system-a LangGraph.

    ┌──────────────┐
    │ input_guard   │
    └──────┬───────┘
           │ (safe?)
    ┌──────▼───────┐     ┌──────────┐
    │  classifier   │     │ BLOCKED  │ → END
    └──────┬───────┘     └──────────┘
           │
    ┌──────▼───────┐
    │  supervisor   │
    └──────┬───────┘
           │ (route)
      ┌────┼────────────┐
      │    │            │
    ┌─▼──┐ ┌▼────────┐ ┌▼────────┐
    │RAG │ │Diagnostic│ │Pricing  │
    └─┬──┘ └┬────────┘ └┬────────┘
      │     │           │
      └─────┼───────────┘
            │
     ┌──────▼───────┐
     │  summarizer   │
     └──────┬───────┘
            │
           END
    """
    graph = StateGraph(AgentState)

    # --- Nodes ---
    graph.add_node("input_guard", input_guard_node)
    graph.add_node("classifier", classifier_node)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("rag_agent", rag_agent_node)
    graph.add_node("diagnostic_agent", diagnostic_agent_node)
    graph.add_node("pricing_agent", pricing_agent_node)
    graph.add_node("summarizer", summarizer_node)

    # Blocked node — returns the guardrail message
    def blocked_node(state: AgentState):
        return {"final_response": f"⚠️ Your query was blocked: {state.get('guardrail_message', 'Policy violation detected.')}"}

    graph.add_node("blocked", blocked_node)

    # --- Entry ---
    graph.set_entry_point("input_guard")

    # --- Edges ---
    graph.add_conditional_edges(
        "input_guard",
        route_after_guard,
        {"classify": "classifier", "blocked": "blocked"},
    )

    graph.add_edge("classifier", "supervisor")

    graph.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        {
            "rag_agent": "rag_agent",
            "diagnostic_agent": "diagnostic_agent",
            "pricing_agent": "pricing_agent",
            "summarizer": "summarizer",
        },
    )

    # All specialists → summarizer
    graph.add_edge("rag_agent", "summarizer")
    graph.add_edge("diagnostic_agent", "summarizer")
    graph.add_edge("pricing_agent", "summarizer")

    # Terminals
    graph.add_edge("summarizer", END)
    graph.add_edge("blocked", END)

    # --- Compile ---
    compiled = graph.compile()
    logger.info("agent-system-a LangGraph compiled ✓")
    return compiled
