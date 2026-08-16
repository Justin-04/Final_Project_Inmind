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
    If BERT is confident (>0.85), trust it and skip LLM call.
    Otherwise, use LLM supervisor for complex routing.
    """
    intent = state.get("intent", "")
    confidence = state.get("confidence", 0.0)

    # Fast path: BERT is confident → route directly (skip LLM call)
    if confidence >= 0.85:
        route_map = {"rag": "rag_agent", "diagnostic": "diagnostic_agent", "pricing": "pricing_agent"}
        route = route_map.get(intent, "rag_agent")
        print(f"\n🎯 [Supervisor] BERT confident ({confidence:.2f}) → fast routing to {route}")
        return {"route": route, "iteration_count": state.get("iteration_count", 0) + 1}

    # Slow path: BERT unsure → LLM decides
    print("\n🎯 [Supervisor] BERT unsure → LLM deciding route...")
    result = _supervisor.route(
        query=state["query"],
        conversation_history=state.get("conversation_history", []),
        iteration_count=state.get("iteration_count", 0),
    )
    print(f"   Route: {result['route']}")
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
    print("\n💰 [Pricing Agent] Calling agent-system-b...")
    result = _pricing_agent.execute(state["query"], state.get("conversation_history", []))
    print(f"   Got {len(result.get('vendors', []))} vendors")
    return {"pricing_result": result}


def summarizer_node(state: AgentState) -> Dict[str, Any]:
    """Synthesize specialist outputs into final response."""
    print("\n✍️  [Summarizer] Generating response...")
    response = _summarizer.synthesize(
        query=state["query"],
        conversation_history=state.get("conversation_history", []),
        rag_result=state.get("rag_result"),
        diagnostic_result=state.get("diagnostic_result"),
        pricing_result=state.get("pricing_result"),
    )

    # Run output guard
    guard_result = _output_guard.validate(response)
    final = guard_result["response"]

    if guard_result.get("warnings"):
        print(f"   ⚠️ Output guard warnings: {guard_result['warnings']}")

    print(f"   ✅ Response ready ({len(final)} chars)")
    return {"final_response": final}
