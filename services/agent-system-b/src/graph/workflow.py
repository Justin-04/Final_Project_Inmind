"""
LangGraph Workflow for agent-system-b

Simple single-node graph: the LLM agent handles the full reasoning loop
internally (tool selection, execution, re-prompting) and returns the final result.
"""

import logging
from langgraph.graph import StateGraph, END
from src.state.agent_state import AgentState
from src.graph.nodes import agent_reasoning_node

logger = logging.getLogger(__name__)


def build_graph():
    """
    Build and compile the agent-system-b workflow.

    Graph Structure (simple — the complexity is inside the agent node):
    ┌───────────────────────┐
    │  agent_reasoning_node │  ← LLM decides tools, calls them, loops, returns answer
    └───────────┬───────────┘
                │
               END

    The agent_reasoning_node internally handles:
    1. Send query + tools to LLM
    2. LLM returns tool_calls → execute → feed results back → repeat
    3. LLM returns final content → parse → done

    Returns:
        Compiled LangGraph application
    """
    graph = StateGraph(AgentState)

    # Single node — the LLM agent with tool loop
    graph.add_node("agent", agent_reasoning_node)

    # Entry and exit
    graph.set_entry_point("agent")
    graph.add_edge("agent", END)

    compiled = graph.compile()
    logger.info("agent-system-b workflow compiled (LLM agent with tool-calling)")
    return compiled
