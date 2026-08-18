"""
LangGraph Workflow for agent-system-a.

Full pipeline:
  input_guard → classifier → supervisor → [multi_router] → summarizer → END

Multi-router supports calling multiple specialist agents for queries that span domains.
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
    """Route based on supervisor decision."""
    routes = state.get("routes", [state.get("route", "rag_agent")])

    # If only one route and it's summarizer (general query), go directly
    if routes == ["summarizer"]:
        return "summarizer"

    # Otherwise go through multi_router
    return "multi_router"


def multi_router_node(state: AgentState) -> dict:
    """
    Execute all agents in the routes list sequentially.
    This enables multi-domain queries (e.g., specs + error code).
    """
    routes = state.get("routes", [state.get("route", "rag_agent")])
    results = {}

    print(f"\n  [Multi-Router] Executing {len(routes)} agent(s): {routes}")

    for route in routes:
        if route == "rag_agent":
            result = rag_agent_node(state)
            results.update(result)
        elif route == "diagnostic_agent":
            result = diagnostic_agent_node(state)
            results.update(result)
        elif route == "pricing_agent":
            result = pricing_agent_node(state)
            results.update(result)

    return results


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
           │ (routes)
    ┌──────▼───────┐
    │ multi_router  │  ← calls 1+ agents based on routes list
    └──────┬───────┘
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
    graph.add_node("multi_router", multi_router_node)
    graph.add_node("summarizer", summarizer_node)

    # Blocked node — returns the guardrail message
    def blocked_node(state: AgentState):
        return {"final_response": "Your query was blocked: " + (state.get('guardrail_message') or 'Policy violation detected.')}

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
            "multi_router": "multi_router",
            "summarizer": "summarizer",
        },
    )

    # Multi-router → summarizer
    graph.add_edge("multi_router", "summarizer")

    # Terminals
    graph.add_edge("summarizer", END)
    graph.add_edge("blocked", END)

    # --- Compile ---
    compiled = graph.compile()
    logger.info("agent-system-a LangGraph compiled (multi-route enabled)")
    return compiled
