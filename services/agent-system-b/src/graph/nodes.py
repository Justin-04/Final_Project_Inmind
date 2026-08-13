"""
LangGraph Node Functions for agent-system-b

The agent loop: LLM reasons → calls tools → processes results → repeats or finishes.
"""

import os
import json
import logging
from typing import Dict, Any

from langfuse.openai import OpenAI
from src.state.agent_state import AgentState
from src.tools import TOOL_DEFINITIONS, TOOL_REGISTRY

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL = os.getenv("AGENT_B_MODEL", "gpt-4o-mini")


def agent_reasoning_node(state: AgentState) -> Dict[str, Any]:
    """
    Core LLM agent node.

    The LLM receives the user query + conversation history, decides which
    tools to call, executes them, and loops until it produces a final answer.

    This node handles the full tool-calling loop internally:
    1. Send messages to LLM with available tools
    2. If LLM returns tool_calls → execute them, append results, re-send
    3. If LLM returns content (no tool_calls) → done, extract final response

    Updates state:
    - vendors: list
    - confidence: float
    - final_response: dict
    - errors: list
    """
    logger.info("agent_reasoning_node: starting LLM reasoning loop")

    drone_model = state.get("drone_model", "")
    query = state.get("search_query") or state.get("part_category") or ""
    currency = state.get("currency", "USD")

    # Build the system prompt
    system_prompt = f"""You are a DJI drone pricing research agent. Your job is to find
current, accurate pricing information for DJI drones across major retailers.

You have access to tools for web searching, price comparison, stock checking,
and a reference pricing database.

CRITICAL INSTRUCTIONS:
1. ALWAYS call get_reference_pricing FIRST to get baseline pricing data.
2. Then use search_duckduckgo to find real product page URLs for each retailer.
3. Use check_stock_and_delivery if the user asks about stock or delivery.
4. Use compare_prices if you need to analyze price differences.

MANDATORY RULES:
- You MUST include ALL 4 retailers in your response: DJI Store, Amazon, B&H Photo, Best Buy.
- Never skip a retailer. If you have no data for one, include it with null values.
- If search_duckduckgo returns a URL for a retailer, use THAT URL instead of the reference URL.
- DO NOT use site: operators in search queries. Just include the retailer name.

When you have enough information, provide your final answer as a JSON object with this exact structure:
{{
  "drone_model": "{drone_model}",
  "display_name": "<human readable name>",
  "currency": "{currency}",
  "vendors": [
    {{
      "name": "DJI Store",
      "base_price": <number or null>,
      "fly_more_combo": <number or null>,
      "fly_more_combo_plus": <number or null>,
      "care_refresh_1yr": <number or null>,
      "care_refresh_2yr": <number or null>,
      "in_stock": <true/false/null>,
      "delivery_estimate": "<string or null>",
      "url": "<string or null>"
    }},
    {{
      "name": "Amazon",
      ...same fields...
    }},
    {{
      "name": "B&H Photo",
      ...same fields...
    }},
    {{
      "name": "Best Buy",
      ...same fields...
    }}
  ],
  "summary_notes": "<brief summary of findings and recommendations>"
}}

You MUST return exactly 4 vendors. Return ONLY the JSON object, no markdown fences."""

    # Initialize messages
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Find pricing for: {drone_model}. User query: {query}. Currency: {currency}"},
    ]

    client = OpenAI(api_key=OPENAI_API_KEY)
    max_iterations = 8  # Safety limit on tool-calling loops
    iteration = 0

    try:
        while iteration < max_iterations:
            iteration += 1
            print(f"\n{'='*60}")
            print(f"  🔄 LLM ITERATION {iteration}/{max_iterations}")
            print(f"{'='*60}")

            # Call LLM with tools
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=TOOL_DEFINITIONS,
                tool_choice="auto",
                temperature=0.1,
            )

            choice = response.choices[0]
            message = choice.message

            # If the LLM wants to call tools
            if message.tool_calls:
                # Append the assistant message (with tool_calls)
                messages.append(message.model_dump())

                print(f"\n  🛠️  LLM wants to call {len(message.tool_calls)} tool(s):")

                # Execute each tool call
                for tool_call in message.tool_calls:
                    func_name = tool_call.function.name
                    func_args = json.loads(tool_call.function.arguments)

                    print(f"\n  ┌─ Tool: {func_name}")
                    print(f"  │  Args: {json.dumps(func_args)[:200]}")

                    # Execute the tool
                    tool_fn = TOOL_REGISTRY.get(func_name)
                    if tool_fn:
                        try:
                            result = tool_fn(**func_args)
                        except Exception as e:
                            result = {"error": str(e)}
                    else:
                        result = {"error": f"Unknown tool: {func_name}"}

                    result_str = json.dumps(result, default=str)
                    print(f"  │  Result: {result_str[:300]}")
                    if len(result_str) > 300:
                        print(f"  │  ... ({len(result_str)} chars total)")
                    print(f"  └─ Done")

                    # Append tool result
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result_str,
                    })

            else:
                # No tool calls — LLM is done reasoning, parse final answer
                final_text = message.content or ""
                print(f"\n  ✅ LLM FINISHED after {iteration} iterations")
                print(f"  📝 Final response ({len(final_text)} chars):")
                print(f"     {final_text[:500]}")
                if len(final_text) > 500:
                    print(f"     ... (truncated)")

                # Parse the JSON response
                parsed = _parse_final_response(final_text, drone_model, currency)
                
                print(f"\n  📊 Parsed result:")
                print(f"     Vendors: {len(parsed.get('vendors', []))}")
                for v in parsed.get('vendors', []):
                    print(f"       - {v.get('name')}: ${v.get('base_price')} | combo=${v.get('fly_more_combo')}")
                if parsed.get('summary_notes'):
                    print(f"     Summary: {parsed['summary_notes'][:150]}")

                # Log to Langfuse via metadata in the next LLM call
                return {
                    "vendors": parsed.get("vendors", []),
                    "confidence": 0.9 if parsed.get("vendors") else 0.3,
                    "final_response": parsed,
                    "errors": [],
                }

        # If we hit max iterations
        print(f"\n  ⚠️  HIT MAX ITERATIONS ({max_iterations}) — forcing stop")
        return {
            "vendors": [],
            "confidence": 0.0,
            "final_response": {"error": "Agent exceeded maximum reasoning iterations"},
            "errors": ["Max iterations reached"],
        }

    except Exception as e:
        print(f"\n  ❌ ERROR: {e}")
        logger.error(f"agent_reasoning_node error: {e}")
        return {
            "vendors": [],
            "confidence": 0.0,
            "final_response": {"error": str(e)},
            "errors": [str(e)],
        }


def _parse_final_response(text: str, drone_model: str, currency: str) -> Dict[str, Any]:
    """
    Parse the LLM's final JSON response.

    Handles cases where the LLM wraps JSON in markdown fences or adds extra text.
    """
    # Try to extract JSON from the text
    # Strip markdown fences if present
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Remove opening fence (```json or ```)
        first_newline = cleaned.index("\n")
        cleaned = cleaned[first_newline + 1:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find JSON object in the text
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

    # If all parsing fails, return raw text as summary
    return {
        "drone_model": drone_model,
        "display_name": drone_model.replace("_", " ").title(),
        "currency": currency,
        "vendors": [],
        "summary_notes": text[:500],
        "parse_error": "Could not parse LLM response as JSON",
    }
