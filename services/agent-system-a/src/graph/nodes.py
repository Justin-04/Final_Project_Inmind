"""
LangGraph Node Functions for agent-system-a.

Each node is a thin wrapper that calls the corresponding class in
src/pipeline/ or src/agents/. Keeps the graph clean and logic testable.
"""

from typing import Dict, Any
from src.state.agent_state import AgentState
from src.pipeline import InputGuard, Supervisor, OutputGuard
from src.pipeline.classifier import IntentClassifier
from src.agents import RAGAgent, DiagnosticAgent, PricingAgent, Summarizer
from src.agents.tutorial_agent import TutorialAgent


from src.pipeline.input_guard_v2 import InputGuardV2




# Instantiate once (singletons)
# _input_guard = InputGuard()

_input_guard = InputGuardV2()

_classifier = IntentClassifier()
_supervisor = Supervisor(max_iterations=5)
_output_guard = OutputGuard()
_rag_agent = RAGAgent()
_diagnostic_agent = DiagnosticAgent()
_pricing_agent = PricingAgent()
_tutorial_agent = TutorialAgent()
_summarizer = Summarizer()


# ─────────────────────────────────────────────────────────────────────────────

def input_guard_node(state: AgentState) -> Dict[str, Any]:
    """Run LLM-powered input safety check."""
    print("\n🛡️  [Input Guard] Checking query safety...")
    result = _input_guard.check(state["query"])
    print(f"   {'✅ Safe' if result['safe'] else '❌ Blocked: ' + str(result['reason'])}")
    return {
        "input_safe": result["safe"],
        "guardrail_message": result.get("reason"),
    }


def classifier_node(state: AgentState) -> Dict[str, Any]:
    """BERT intent classification (fast ~50ms). Used as pre-filter for supervisor."""
    print("\n🏷️  [Classifier] BERT classifying intent...")
    result = _classifier.classify(state["query"], state.get("conversation_history", []))
    print(f"   Intent: {result['intent']} (conf={result['confidence']}, method={result['method']})")
    return {"intent": result["intent"], "confidence": result["confidence"]}


def supervisor_node(state: AgentState) -> Dict[str, Any]:
    """
    LLM-powered routing decision.
    If use_bert=True and BERT is confident (>0.85), trust it and skip LLM call.
    If use_bert=False, always use LLM supervisor.
    Otherwise, use LLM supervisor for complex routing (supports multi-route).

    Special case: if query contains an error code pattern AND other content,
    force multi-route through LLM supervisor regardless of BERT confidence.
    """
    import re
    intent = state.get("intent", "")
    confidence = state.get("confidence", 0.0)
    query = state.get("query", "")
    use_bert = state.get("use_bert", True)

    # Detect if query contains error code pattern (E001, E003, etc.)
    has_error_code = bool(re.search(r'\bE\d{3}\b', query, re.IGNORECASE))
    # Detect if query also has non-diagnostic content (multi-domain)
    query_words = len(query.split())
    is_multi_domain = has_error_code and query_words > 5 and intent != "diagnostic"

    # If multi-domain detected, skip BERT and let LLM supervisor decide routes
    if is_multi_domain:
        print(f"\n  [Supervisor] Multi-domain detected (error code + other content) -> LLM deciding routes...")
        result = _supervisor.route(
            query=query,
            conversation_history=state.get("conversation_history", []),
            iteration_count=state.get("iteration_count", 0),
        )
        print(f"   Routes: {result.get('routes', [result.get('route')])}")
        return result

    # Fast path: BERT enabled AND confident → route directly (skip LLM call)
    if use_bert and confidence >= 0.85:
        route_map = {"rag": "rag_agent", "diagnostic": "diagnostic_agent", "pricing": "pricing_agent"}
        route = route_map.get(intent, "rag_agent")
        print(f"\n  [Supervisor] BERT confident ({confidence:.2f}) -> fast routing to {route}")
        return {"route": route, "routes": [route], "iteration_count": state.get("iteration_count", 0) + 1}

    # Slow path: BERT disabled OR BERT unsure → LLM decides (handles general/greeting queries + multi-route)
    reason = "BERT disabled by user" if not use_bert else f"BERT unsure ({confidence:.2f})"
    print(f"\n  [Supervisor] {reason} -> LLM deciding route...")
    result = _supervisor.route(
        query=query,
        conversation_history=state.get("conversation_history", []),
        iteration_count=state.get("iteration_count", 0),
    )
    print(f"   Routes: {result.get('routes', [result.get('route')])}")
    return result


def rag_agent_node(state: AgentState) -> Dict[str, Any]:
    """LLM-powered RAG agent — plans search strategy and executes."""
    print("\n📚 [RAG Agent] LLM planning search strategy...")
    result = _rag_agent.execute(state["query"], state.get("conversation_history", []))
    print(f"   Retrieved {len(result.get('chunks', []))} chunks")
    return {"rag_result": result}


def diagnostic_agent_node(state: AgentState) -> Dict[str, Any]:
    """LLM-powered diagnostic agent — analyzes problem and executes lookups."""
    print("\n🔧 [Diagnostic Agent] LLM analyzing problem...")
    result = _diagnostic_agent.execute(state["query"], state.get("conversation_history", []))
    print(f"   Found {len(result.get('error_codes', []))} codes, {len(result.get('rag_chunks', []))} chunks")
    return {"diagnostic_result": result}


def pricing_agent_node(state: AgentState) -> Dict[str, Any]:
    """Call agent-system-b for vendor pricing (HTTP A2A)."""
    print("\n  [Pricing Agent] Calling agent-system-b...")
    result = _pricing_agent.execute(state["query"], state.get("conversation_history", []))
    print(f"   Got {len(result.get('vendors', []))} vendors")
    return {"pricing_result": result}


def tutorial_agent_node(state: AgentState) -> Dict[str, Any]:
    """Call agent-system-b for YouTube tutorial search (HTTP A2A)."""
    print("\n  [Tutorial Agent] Searching YouTube tutorials...")
    result = _tutorial_agent.execute(state["query"], state.get("conversation_history", []))
    print(f"   Found {len(result.get('videos', []))} videos")
    return {"tutorial_result": result}


def summarizer_node(state: AgentState) -> Dict[str, Any]:
    """Synthesize specialist outputs into final response."""
    print("\n  [Summarizer] Generating response...")

    # Build tutorial context if available
    tutorial_result = state.get("tutorial_result")
    tutorial_context = ""
    if tutorial_result and tutorial_result.get("videos"):
        videos = tutorial_result["videos"]
        tutorial_context = "\n\nRelevant YouTube tutorials found:\n"
        for i, v in enumerate(videos[:5], 1):
            tutorial_context += f"{i}. [{v.get('title', '')}]({v.get('url', '')})"
            if v.get("channel"):
                tutorial_context += f" — {v['channel']}"
            if v.get("duration"):
                tutorial_context += f" ({v['duration']})"
            tutorial_context += "\n"

    response = _summarizer.synthesize(
        query=state["query"] + tutorial_context,
        conversation_history=state.get("conversation_history", []),
        rag_result=state.get("rag_result"),
        diagnostic_result=state.get("diagnostic_result"),
        pricing_result=state.get("pricing_result"),
    )

    # Run output guard
    guard_result = _output_guard.validate(response)
    final = guard_result["response"]

    if guard_result.get("warnings"):
        print(f"   Output guard warnings: {guard_result['warnings']}")

    print(f"   Response ready ({len(final)} chars)")
    return {"final_response": final}
