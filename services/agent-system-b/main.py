"""
agent-system-b: LLM-Driven Vendor & Pricing Agent

An autonomous agent powered by gpt-4o-mini that uses tool-calling to:
- Search the web for current DJI drone pricing
- Compare prices across retailers
- Check stock and delivery info

Communication: HTTP-only (A2A protocol from agent-system-a).
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import os
import logging
import sys

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from graph.workflow import build_graph
from vendor_agent import VendorAgent

# ─────────────────────────────────────────────────────────────────────────────
# App Setup
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="DJI RAG Agent System B",
    description="LLM-driven pricing agent with DuckDuckGo search tools (gpt-4o-mini)",
    version="2.0.0",
)

# Build the LangGraph workflow
agent_graph = build_graph()

# Fallback deterministic agent (used when OPENAI_API_KEY is not set)
fallback_agent = VendorAgent()

# Model name normalization
MODEL_ALIASES: Dict[str, str] = {
    "mini_4_pro": "DJI Mini 4 Pro",
    "dji_mini_4_pro": "DJI Mini 4 Pro",
    "air_3": "DJI Air 3",
    "dji_air_3": "DJI Air 3",
    "mavic_3_pro": "DJI Mavic 3 Pro",
    "dji_mavic_3_pro": "DJI Mavic 3 Pro",
}


def _normalize_model_key(drone_model: str) -> str:
    """Normalize to internal key format."""
    return drone_model.lower().strip().replace(" ", "_").replace("dji_", "dji_")


def _get_display_name(drone_model: str) -> str:
    """Get human-readable display name."""
    key = _normalize_model_key(drone_model)
    return MODEL_ALIASES.get(key, drone_model.replace("_", " ").title())


# ─────────────────────────────────────────────────────────────────────────────
# Request / Response Models
# ─────────────────────────────────────────────────────────────────────────────

class PricingRequest(BaseModel):
    drone_model: str = Field(..., description="Drone model identifier (e.g., 'mini_4_pro')")
    query: str = Field(..., description="User's pricing/vendor query")
    currency: str = Field(default="USD", description="Target currency code")


class VendorEntry(BaseModel):
    name: str
    base_price: Optional[float] = None
    fly_more_combo: Optional[float] = None
    fly_more_combo_plus: Optional[float] = None
    care_refresh_1yr: Optional[float] = None
    care_refresh_2yr: Optional[float] = None
    in_stock: Optional[bool] = None
    delivery_estimate: Optional[str] = None
    url: Optional[str] = None


class PricingResponse(BaseModel):
    drone_model: str
    display_name: str
    source: str = Field(description="'llm_agent' or 'fallback'")
    currency: str
    vendors: List[VendorEntry] = []
    summary_notes: Optional[str] = None
    error: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "agent-system-b",
        "version": "2.0.0",
        "mode": "llm_agent" if os.getenv("OPENAI_API_KEY") else "fallback",
        "model": os.getenv("AGENT_B_MODEL", "gpt-4o-mini"),
    }


@app.post("/v1/pricing", response_model=PricingResponse)
async def get_pricing(request: PricingRequest):
    """
    Get vendor pricing breakdown for a DJI drone model.

    The LLM agent autonomously:
    1. Analyzes the query to determine what information is needed
    2. Searches the web via DuckDuckGo for current pricing
    3. Compares prices across retailers
    4. Checks stock and delivery when relevant
    5. Returns a structured JSON response

    Falls back to deterministic search if OPENAI_API_KEY is not set.
    """
    try:
        display_name = _get_display_name(request.drone_model)
        model_key = _normalize_model_key(request.drone_model)

        logger.info(f"Pricing request: model={request.drone_model}, query='{request.query[:50]}'")

        # If OpenAI key is available → use LLM agent
        if os.getenv("OPENAI_API_KEY"):
            return await _run_llm_agent(model_key, display_name, request)
        else:
            # Fallback to deterministic agent
            logger.info("No OPENAI_API_KEY — using fallback deterministic agent")
            return await _run_fallback(model_key, display_name, request)

    except Exception as e:
        logger.error(f"Pricing error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Pricing lookup failed: {str(e)}")


async def _run_llm_agent(
    model_key: str, display_name: str, request: PricingRequest
) -> PricingResponse:
    """Run the LLM-driven agent via LangGraph."""

    # Invoke the graph
    result = agent_graph.invoke({
        "drone_model": display_name,
        "search_query": request.query,
        "part_category": None,
        "part_id": None,
        "currency": request.currency,
        "vendors": [],
        "confidence": 0.0,
        "final_response": {},
        "errors": [],
    })

    final = result.get("final_response", {})
    vendors_raw = final.get("vendors", [])

    # Parse vendors into response model
    vendors = []
    for v in vendors_raw:
        vendors.append(VendorEntry(
            name=v.get("name", "Unknown"),
            base_price=v.get("base_price"),
            fly_more_combo=v.get("fly_more_combo"),
            fly_more_combo_plus=v.get("fly_more_combo_plus"),
            care_refresh_1yr=v.get("care_refresh_1yr"),
            care_refresh_2yr=v.get("care_refresh_2yr"),
            in_stock=v.get("in_stock"),
            delivery_estimate=v.get("delivery_estimate"),
            url=v.get("url"),
        ))

    return PricingResponse(
        drone_model=model_key,
        display_name=display_name,
        source="llm_agent",
        currency=request.currency,
        vendors=vendors,
        summary_notes=final.get("summary_notes"),
        error=final.get("error"),
    )


async def _run_fallback(
    model_key: str, display_name: str, request: PricingRequest
) -> PricingResponse:
    """Run the deterministic fallback agent (no LLM)."""

    result = await fallback_agent.get_pricing(
        drone_model=request.drone_model,
        query=request.query,
        currency=request.currency,
    )

    vendors = []
    for v in result.get("vendors", []):
        vendors.append(VendorEntry(**v))

    return PricingResponse(
        drone_model=model_key,
        display_name=display_name,
        source="fallback",
        currency=request.currency,
        vendors=vendors,
        summary_notes=None,
        error=result.get("error"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Legacy endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/v1/vendor-search")
async def vendor_search_legacy(request: dict):
    """Legacy vendor search endpoint."""
    pricing_req = PricingRequest(
        drone_model=request.get("drone_model", ""),
        query=request.get("search_query") or request.get("part_category", "pricing"),
        currency=request.get("currency", "USD"),
    )
    result = await get_pricing(pricing_req)
    return result.model_dump()


@app.get("/api/v1/pricing/{part_id}")
async def get_pricing_by_part_legacy(part_id: str):
    """Legacy pricing by part ID endpoint."""
    pricing_req = PricingRequest(
        drone_model=part_id,
        query=f"pricing for {part_id}",
        currency="USD",
    )
    result = await get_pricing(pricing_req)
    return result.model_dump()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
