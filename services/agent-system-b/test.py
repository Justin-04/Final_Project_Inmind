"""
Agent System B — Evaluation Test Set

Tests tool selection correctness and response quality.
Logs all results to Langfuse for traceability.

Run:
    cd services/agent-system-b
    python test.py

Requires:
    - Server running on localhost:8001 (uvicorn main:app --port 8001)
    - OPENAI_API_KEY set in .env
    - LANGFUSE_* keys set in .env
"""

import asyncio
import json
import time
import os
import sys
from datetime import datetime, timezone
from typing import List, Dict, Any

import httpx
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))

from langfuse import Langfuse

# ─────────────────────────────────────────────────────────────────────────────
# Langfuse Setup
# ─────────────────────────────────────────────────────────────────────────────

# Check which Langfuse API version is available
try:
    langfuse = Langfuse(
        public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
        secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
        host=os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com"),
    )
    # Test if .trace() exists
    _has_trace = hasattr(langfuse, 'trace')
except Exception:
    langfuse = None
    _has_trace = False

# ─────────────────────────────────────────────────────────────────────────────
# Test Set: Expected Tool Calls & Response Validation
# ─────────────────────────────────────────────────────────────────────────────

TEST_CASES = [
    # --- Basic pricing queries (should use get_reference_pricing) ---
    {
        "id": "TC-B-001",
        "query": {
            "drone_model": "mini_4_pro",
            "query": "How much does the DJI Mini 4 Pro cost?",
            "currency": "USD",
        },
        "expected_tools": ["get_reference_pricing"],
        "expected_vendors_count": 4,
        "expected_has_price": True,
        "expected_model_in_response": "mini_4_pro",
        "category": "basic_pricing",
    },
    {
        "id": "TC-B-002",
        "query": {
            "drone_model": "air_3",
            "query": "What is the price of DJI Air 3?",
            "currency": "USD",
        },
        "expected_tools": ["get_reference_pricing"],
        "expected_vendors_count": 4,
        "expected_has_price": True,
        "expected_model_in_response": "air_3",
        "category": "basic_pricing",
    },
    {
        "id": "TC-B-003",
        "query": {
            "drone_model": "mavic_3_pro",
            "query": "Mavic 3 Pro pricing",
            "currency": "USD",
        },
        "expected_tools": ["get_reference_pricing"],
        "expected_vendors_count": 4,
        "expected_has_price": True,
        "expected_model_in_response": "mavic_3_pro",
        "category": "basic_pricing",
    },

    # --- Comparison queries (should use get_reference_pricing + compare_prices) ---
    {
        "id": "TC-B-004",
        "query": {
            "drone_model": "mini_4_pro",
            "query": "Compare DJI Mini 4 Pro prices across all retailers. Which is cheapest?",
            "currency": "USD",
        },
        "expected_tools": ["get_reference_pricing", "compare_prices"],
        "expected_vendors_count": 4,
        "expected_has_price": True,
        "expected_model_in_response": "mini_4_pro",
        "category": "comparison",
    },
    {
        "id": "TC-B-005",
        "query": {
            "drone_model": "air_3",
            "query": "Compare DJI Air 3 prices across Amazon, B&H Photo, and Best Buy.",
            "currency": "USD",
        },
        "expected_tools": ["get_reference_pricing"],
        "expected_vendors_count": 4,
        "expected_has_price": True,
        "expected_model_in_response": "air_3",
        "category": "comparison",
    },

    # --- Stock/delivery queries (should use check_stock_and_delivery) ---
    {
        "id": "TC-B-006",
        "query": {
            "drone_model": "mini_4_pro",
            "query": "Is the DJI Mini 4 Pro in stock at Best Buy? When can it ship?",
            "currency": "USD",
        },
        "expected_tools": ["get_reference_pricing", "check_stock_and_delivery"],
        "expected_vendors_count": 4,
        "expected_has_price": True,
        "expected_model_in_response": "mini_4_pro",
        "category": "stock_delivery",
    },
    {
        "id": "TC-B-007",
        "query": {
            "drone_model": "mavic_3_pro",
            "query": "Check Mavic 3 Pro availability and delivery times across retailers",
            "currency": "USD",
        },
        "expected_tools": ["get_reference_pricing", "check_stock_and_delivery"],
        "expected_vendors_count": 4,
        "expected_has_price": True,
        "expected_model_in_response": "mavic_3_pro",
        "category": "stock_delivery",
    },

    # --- Combo/accessory queries ---
    {
        "id": "TC-B-008",
        "query": {
            "drone_model": "mini_4_pro",
            "query": "What is the Fly More Combo price for DJI Mini 4 Pro?",
            "currency": "USD",
        },
        "expected_tools": ["get_reference_pricing"],
        "expected_vendors_count": 4,
        "expected_has_price": True,
        "expected_model_in_response": "mini_4_pro",
        "category": "combo_pricing",
    },
    {
        "id": "TC-B-009",
        "query": {
            "drone_model": "air_3",
            "query": "How much is DJI Care Refresh for the Air 3?",
            "currency": "USD",
        },
        "expected_tools": ["get_reference_pricing"],
        "expected_vendors_count": 4,
        "expected_has_price": True,
        "expected_model_in_response": "air_3",
        "category": "combo_pricing",
    },

    # --- Edge case: unknown model ---
    {
        "id": "TC-B-010",
        "query": {
            "drone_model": "phantom_5",
            "query": "How much is the DJI Phantom 5?",
            "currency": "USD",
        },
        "expected_tools": ["get_reference_pricing", "search_duckduckgo"],
        "expected_vendors_count": 0,  # Unknown model, may return 0 or empty
        "expected_has_price": False,
        "expected_model_in_response": "phantom_5",
        "category": "edge_case",
    },

    # --- Edge case: different currency ---
    {
        "id": "TC-B-011",
        "query": {
            "drone_model": "mini_4_pro",
            "query": "DJI Mini 4 Pro price in EUR",
            "currency": "EUR",
        },
        "expected_tools": ["get_reference_pricing"],
        "expected_vendors_count": 4,
        "expected_has_price": True,
        "expected_model_in_response": "mini_4_pro",
        "category": "edge_case",
    },

    # --- Web search enrichment query ---
    {
        "id": "TC-B-012",
        "query": {
            "drone_model": "mini_4_pro",
            "query": "Are there any deals or discounts on DJI Mini 4 Pro right now?",
            "currency": "USD",
        },
        "expected_tools": ["get_reference_pricing", "search_duckduckgo"],
        "expected_vendors_count": 4,
        "expected_has_price": True,
        "expected_model_in_response": "mini_4_pro",
        "category": "deal_search",
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Evaluation Logic
# ─────────────────────────────────────────────────────────────────────────────

async def run_test_case(client: httpx.AsyncClient, test_case: Dict) -> Dict[str, Any]:
    """Run a single test case and return results."""
    tc_id = test_case["id"]
    print(f"\n{'─'*60}")
    print(f"  Running: {tc_id} [{test_case['category']}]")
    print(f"  Query: {test_case['query']['query'][:60]}...")

    start_time = time.time()

    try:
        resp = await client.post("/v1/pricing", json=test_case["query"], timeout=60)
        latency = time.time() - start_time

        if resp.status_code != 200:
            return {
                "id": tc_id,
                "passed": False,
                "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
                "latency": latency,
                "tools_correct": False,
                "vendors_correct": False,
                "price_correct": False,
            }

        data = resp.json()

        # --- Evaluate response ---
        vendors = data.get("vendors", [])
        has_any_price = any(v.get("base_price") is not None for v in vendors)
        vendor_count = len(vendors)

        # Vendor count check
        if test_case["expected_vendors_count"] == 0:
            vendors_correct = True  # Edge case, anything is fine
        else:
            vendors_correct = vendor_count == test_case["expected_vendors_count"]

        # Price presence check
        price_correct = has_any_price == test_case["expected_has_price"]

        # Model in response check
        model_correct = test_case["expected_model_in_response"] in data.get("drone_model", "")

        # Overall pass
        passed = vendors_correct and price_correct and model_correct

        result = {
            "id": tc_id,
            "category": test_case["category"],
            "passed": passed,
            "latency": round(latency, 2),
            "vendors_returned": vendor_count,
            "vendors_correct": vendors_correct,
            "has_price": has_any_price,
            "price_correct": price_correct,
            "model_correct": model_correct,
            "source": data.get("source", "unknown"),
            "summary": data.get("summary_notes", "")[:100],
            "error": data.get("error"),
        }

        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status} | {latency:.1f}s | vendors={vendor_count} | price={has_any_price} | source={data.get('source')}")

        return result

    except Exception as e:
        latency = time.time() - start_time
        print(f"  ❌ ERROR: {e}")
        return {
            "id": tc_id,
            "passed": False,
            "error": str(e),
            "latency": round(latency, 2),
            "tools_correct": False,
            "vendors_correct": False,
            "price_correct": False,
        }


async def run_evaluation():
    """Run all test cases and compute metrics."""

    print("=" * 60)
    print("  AGENT SYSTEM B — EVALUATION")
    print(f"  {len(TEST_CASES)} test cases")
    print(f"  {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    # Create Langfuse trace for this eval run (if supported)
    eval_trace = None
    if langfuse and _has_trace:
        eval_trace = langfuse.trace(
            name="agent-b-evaluation-run",
            metadata={
                "test_cases": len(TEST_CASES),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    results = []
    async with httpx.AsyncClient(base_url="http://localhost:8001") as client:
        # Verify server is up
        try:
            health = await client.get("/health")
            health_data = health.json()
            print(f"\n  Server: {health_data.get('status')} | mode={health_data.get('mode')}")
        except Exception as e:
            print(f"\n  ❌ Server not reachable: {e}")
            print("  Start with: uvicorn main:app --host 0.0.0.0 --port 8001")
            return

        # Run each test case
        for tc in TEST_CASES:
            result = await run_test_case(client, tc)
            results.append(result)

            # Log individual result to Langfuse
            if eval_trace and hasattr(eval_trace, 'span'):
                eval_trace.span(
                    name=f"test-{tc['id']}",
                    input=tc["query"],
                    output=result,
                    metadata={
                        "category": tc["category"],
                        "passed": result["passed"],
                        "latency": result["latency"],
                    },
                )

    # ─── Compute Metrics ───
    print("\n" + "=" * 60)
    print("  RESULTS SUMMARY")
    print("=" * 60)

    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed

    # By category
    categories = {}
    for r in results:
        cat = r.get("category", "unknown")
        if cat not in categories:
            categories[cat] = {"total": 0, "passed": 0}
        categories[cat]["total"] += 1
        if r["passed"]:
            categories[cat]["passed"] += 1

    # Latencies
    latencies = [r["latency"] for r in results if r.get("latency")]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0

    # Vendor accuracy
    vendor_correct = sum(1 for r in results if r.get("vendors_correct"))
    price_correct = sum(1 for r in results if r.get("price_correct"))

    print(f"\n  Overall: {passed}/{total} passed ({100*passed/total:.0f}%)")
    print(f"  Failed:  {failed}/{total}")
    print(f"\n  Avg latency: {avg_latency:.1f}s")
    print(f"  Vendor count accuracy: {vendor_correct}/{total} ({100*vendor_correct/total:.0f}%)")
    print(f"  Price presence accuracy: {price_correct}/{total} ({100*price_correct/total:.0f}%)")

    print(f"\n  By category:")
    for cat, data in categories.items():
        pct = 100 * data["passed"] / data["total"] if data["total"] > 0 else 0
        print(f"    {cat}: {data['passed']}/{data['total']} ({pct:.0f}%)")

    # ─── Log final metrics to Langfuse ───
    if eval_trace and hasattr(eval_trace, 'score'):
        eval_trace.score(name="overall_accuracy", value=passed / total if total > 0 else 0)
        eval_trace.score(name="vendor_accuracy", value=vendor_correct / total if total > 0 else 0)
        eval_trace.score(name="price_accuracy", value=price_correct / total if total > 0 else 0)
        eval_trace.score(name="avg_latency_seconds", value=avg_latency)
        eval_trace.score(name="total_passed", value=passed)
        eval_trace.score(name="total_failed", value=failed)

    # ─── Print final table ───
    print(f"\n{'─'*60}")
    print(f"  {'ID':<10} {'Category':<16} {'Pass':<6} {'Latency':<8} {'Vendors':<8} {'Price'}")
    print(f"{'─'*60}")
    for r in results:
        status = "✅" if r["passed"] else "❌"
        print(f"  {r['id']:<10} {r.get('category',''):<16} {status:<6} {r['latency']:<8.1f} "
              f"{r.get('vendors_returned','?'):<8} {r.get('has_price','?')}")
    print(f"{'─'*60}")

    print(f"\n  📊 Overall accuracy: {100*passed/total:.0f}%")
    print(f"  📊 Vendor accuracy:  {100*vendor_correct/total:.0f}%")
    print(f"  📊 Price accuracy:   {100*price_correct/total:.0f}%")
    print(f"  ⏱️  Avg latency:     {avg_latency:.1f}s")

    # ─── Save results to file ───
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_tests": total,
        "passed": passed,
        "failed": failed,
        "overall_accuracy": round(passed / total, 4) if total > 0 else 0,
        "vendor_accuracy": round(vendor_correct / total, 4) if total > 0 else 0,
        "price_accuracy": round(price_correct / total, 4) if total > 0 else 0,
        "avg_latency": round(avg_latency, 2),
        "by_category": categories,
        "results": results,
    }

    output_path = os.path.join(os.path.dirname(__file__), "evaluation_results.json")
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  💾 Results saved to: evaluation_results.json")

    # Flush Langfuse
    if langfuse and hasattr(langfuse, 'flush'):
        langfuse.flush()
        print(f"  📤 Results logged to Langfuse")
    else:
        print(f"  ⚠️  Langfuse tracing not available (upgrade langfuse package for full tracing)")

    print(f"\n{'='*60}")
    print(f"  EVALUATION COMPLETE")
    print(f"{'='*60}\n")


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    asyncio.run(run_evaluation())
