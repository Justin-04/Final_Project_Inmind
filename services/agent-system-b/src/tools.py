"""
Agent Tools for agent-system-b

These are the actual tool implementations that the LLM agent can invoke.
Each tool performs a specific action and returns structured data.
"""

import os
import re
import logging
from typing import List, Dict, Any

# from duckduckgo_search import DDGS  # Commented out — replaced by Google Custom Search

logger = logging.getLogger(__name__)

# Google Custom Search API config
GOOGLE_CSE_API_KEY = os.getenv("GOOGLE_CSE_API_KEY", "")
GOOGLE_CSE_CX = os.getenv("GOOGLE_CSE_CX", "")  # Custom Search Engine ID

# Retailers config
RETAILERS = [
    {"name": "DJI Store", "site": "store.dji.com"},
    {"name": "Amazon", "site": "amazon.com"},
    {"name": "B&H Photo", "site": "bhphotovideo.com"},
    {"name": "Best Buy", "site": "bestbuy.com"},
]


def search_duckduckgo(query: str) -> List[Dict[str, str]]:
    """
    Execute a web search using Google Custom Search API.
    (Function name kept as search_duckduckgo for backward compatibility with LLM tool definitions)

    Args:
        query: Search query string (e.g., "DJI Air 3 price Amazon")

    Returns:
        list: Up to 8 search results, each with 'title', 'url', 'snippet', 'prices_found'.
    """
    logger.info(f"[Tool] search (Google CSE): '{query}'")

    # Use SerpAPI (Google Search) if key available
    if os.getenv("SERPAPI_KEY"):
        return _google_search(query)

    # Fallback to DuckDuckGo if no SerpAPI key
    return _duckduckgo_search(query)


def _google_search(query: str) -> List[Dict[str, str]]:
    """Execute search via SerpAPI (Google Search wrapper)."""
    try:
        from serpapi import GoogleSearch

        params = {
            "engine": "google",
            "q": query,
            "api_key": os.getenv("SERPAPI_KEY", ""),
            "num": 8,
        }

        search = GoogleSearch(params)
        data = search.get_dict()

        if "error" in data:
            logger.error(f"[Tool] SerpAPI error: {data['error']}")
            return []

        results = []
        for item in data.get("organic_results", []):
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            combined_text = f"{title} {snippet}"

            # Extract dollar prices
            prices = re.findall(r'\$[\d,]+\.?\d*', combined_text)
            parsed_prices = []
            for p in prices:
                try:
                    val = float(p.replace("$", "").replace(",", ""))
                    if 10 < val < 15000:
                        parsed_prices.append(val)
                except ValueError:
                    pass

            results.append({
                "title": title,
                "url": item.get("link", ""),
                "snippet": snippet,
                "prices_found": parsed_prices,
            })

        logger.info(f"[Tool] SerpAPI: returned {len(results)} results")
        return results

    except Exception as e:
        logger.error(f"[Tool] SerpAPI error: {e}")
        return [{"title": "Search failed", "url": "", "snippet": str(e), "prices_found": []}]


def _duckduckgo_search(query: str) -> List[Dict[str, str]]:
    """Fallback: DuckDuckGo search (unreliable, rate-limited)."""
    try:
        from duckduckgo_search import DDGS
        ddgs = DDGS()
        raw_results = ddgs.text(query, max_results=8)

        if not raw_results and "site:" in query:
            clean_query = re.sub(r'site:\S+', '', query).strip()
            raw_results = ddgs.text(clean_query, max_results=8)

        results = []
        for r in raw_results:
            snippet = r.get("body", "")
            title = r.get("title", "")
            combined_text = f"{title} {snippet}"

            prices = re.findall(r'\$[\d,]+\.?\d*', combined_text)
            parsed_prices = []
            for p in prices:
                try:
                    val = float(p.replace("$", "").replace(",", ""))
                    if 10 < val < 15000:
                        parsed_prices.append(val)
                except ValueError:
                    pass

            results.append({
                "title": title,
                "url": r.get("href", ""),
                "snippet": snippet,
                "prices_found": parsed_prices,
            })

        logger.info(f"[Tool] DuckDuckGo: returned {len(results)} results")
        return results

    except Exception as e:
        logger.error(f"[Tool] DuckDuckGo error: {e}")
        return [{"title": "Search failed", "url": "", "snippet": str(e), "prices_found": []}]


def compare_prices(retailers_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Structure and compare price variances across retailers.

    Args:
        retailers_data: List of dicts, each with:
            - name (str): Retailer name
            - base_price (float|None)
            - fly_more_combo (float|None)
            - url (str|None)

    Returns:
        dict: Comparison analysis with cheapest, most expensive, average, and savings.
    """
    logger.info(f"[Tool] compare_prices: {len(retailers_data)} retailers")

    # Filter out entries without a base price
    priced = [r for r in retailers_data if r.get("base_price") is not None]

    if not priced:
        return {
            "comparison_available": False,
            "message": "No valid prices found to compare",
            "retailers": retailers_data,
        }

    prices = [r["base_price"] for r in priced]
    cheapest = min(priced, key=lambda x: x["base_price"])
    most_expensive = max(priced, key=lambda x: x["base_price"])
    avg_price = sum(prices) / len(prices)
    savings = most_expensive["base_price"] - cheapest["base_price"]

    return {
        "comparison_available": True,
        "cheapest": {"name": cheapest["name"], "price": cheapest["base_price"], "url": cheapest.get("url")},
        "most_expensive": {"name": most_expensive["name"], "price": most_expensive["base_price"]},
        "average_price": round(avg_price, 2),
        "max_savings": round(savings, 2),
        "all_prices": [{"name": r["name"], "base_price": r["base_price"]} for r in priced],
    }


def check_stock_and_delivery(drone_model: str) -> List[Dict[str, Any]]:
    """
    Search for stock availability and shipping estimates across retailers.

    Args:
        drone_model: Human-readable drone model (e.g., "DJI Mini 4 Pro")

    Returns:
        list: Per-retailer stock and delivery info.
    """
    logger.info(f"[Tool] check_stock_and_delivery: '{drone_model}'")

    results = []

    for retailer in RETAILERS:
        entry = {
            "name": retailer["name"],
            "in_stock": None,
            "delivery_estimate": None,
            "url": None,
        }

        try:
            query = f"{drone_model} buy {retailer['name']} in stock"
            search_results = search_duckduckgo(query)

            if search_results:
                entry["url"] = search_results[0].get("url")
                combined = " ".join(
                    f"{r.get('title', '')} {r.get('snippet', '')}" for r in search_results
                ).lower()

                # Stock detection
                if "in stock" in combined or "add to cart" in combined or "buy now" in combined:
                    entry["in_stock"] = True
                elif "out of stock" in combined or "sold out" in combined or "unavailable" in combined:
                    entry["in_stock"] = False

                # Delivery detection
                delivery_match = re.search(r'(\d+[-–]\d+\s*(?:business\s*)?days)', combined)
                if delivery_match:
                    entry["delivery_estimate"] = delivery_match.group(1)
                elif "free shipping" in combined:
                    entry["delivery_estimate"] = "Free shipping available"
                elif "next day" in combined or "next-day" in combined:
                    entry["delivery_estimate"] = "Next day delivery available"

        except Exception as e:
            logger.warning(f"[Tool] check_stock_and_delivery failed for {retailer['name']}: {e}")

        results.append(entry)

    return results


def get_reference_pricing(drone_model: str) -> Dict[str, Any]:
    """
    Get verified reference/baseline pricing for a DJI drone model from our database.

    Use this tool FIRST or when web search returns no useful pricing data.
    It provides known prices, combo options, Care Refresh costs, and retailer URLs.

    Args:
        drone_model: Drone model name (e.g., "DJI Mini 4 Pro", "mini_4_pro", "air_3")

    Returns:
        dict: Reference pricing data with prices and vendor URLs.
    """
    logger.info(f"[Tool] get_reference_pricing: '{drone_model}'")

    key = drone_model.lower().strip().replace(" ", "_")
    alias_map = {
        "mini_4_pro": "dji_mini_4_pro",
        "dji_mini_4_pro": "dji_mini_4_pro",
        "air_3": "dji_air_3",
        "dji_air_3": "dji_air_3",
        "mavic_3_pro": "dji_mavic_3_pro",
        "dji_mavic_3_pro": "dji_mavic_3_pro",
    }
    key = alias_map.get(key, key)

    REFERENCE_DATA = {
        "dji_mini_4_pro": {
            "display_name": "DJI Mini 4 Pro",
            "base_price": 759.00,
            "fly_more_combo": 959.00,
            "fly_more_combo_plus": 1099.00,
            "care_refresh_1yr": 79.00,
            "care_refresh_2yr": 129.00,
            "vendors": [
                {"name": "DJI Store", "url": "https://store.dji.com/product/dji-mini-4-pro"},
                {"name": "Amazon", "url": "https://www.amazon.com/s?k=DJI+Mini+4+Pro"},
                {"name": "B&H Photo", "url": "https://www.bhphotovideo.com/c/search?q=DJI+Mini+4+Pro"},
                {"name": "Best Buy", "url": "https://www.bestbuy.com/site/searchpage.jsp?st=DJI+Mini+4+Pro"},
            ],
        },
        "dji_air_3": {
            "display_name": "DJI Air 3",
            "base_price": 1099.00,
            "fly_more_combo": 1349.00,
            "fly_more_combo_plus": None,
            "care_refresh_1yr": 99.00,
            "care_refresh_2yr": 159.00,
            "vendors": [
                {"name": "DJI Store", "url": "https://store.dji.com/product/dji-air-3"},
                {"name": "Amazon", "url": "https://www.amazon.com/s?k=DJI+Air+3"},
                {"name": "B&H Photo", "url": "https://www.bhphotovideo.com/c/search?q=DJI+Air+3"},
                {"name": "Best Buy", "url": "https://www.bestbuy.com/site/searchpage.jsp?st=DJI+Air+3"},
            ],
        },
        "dji_mavic_3_pro": {
            "display_name": "DJI Mavic 3 Pro",
            "base_price": 2199.00,
            "fly_more_combo": 2999.00,
            "fly_more_combo_plus": None,
            "care_refresh_1yr": 189.00,
            "care_refresh_2yr": 299.00,
            "vendors": [
                {"name": "DJI Store", "url": "https://store.dji.com/product/dji-mavic-3-pro"},
                {"name": "Amazon", "url": "https://www.amazon.com/s?k=DJI+Mavic+3+Pro"},
                {"name": "B&H Photo", "url": "https://www.bhphotovideo.com/c/search?q=DJI+Mavic+3+Pro"},
                {"name": "Best Buy", "url": "https://www.bestbuy.com/site/searchpage.jsp?st=DJI+Mavic+3+Pro"},
            ],
        },
    }

    data = REFERENCE_DATA.get(key)
    if data:
        # Return full pricing for ALL vendors (MSRP is the same across retailers)
        vendor_list = []
        for v in data["vendors"]:
            vendor_list.append({
                "name": v["name"],
                "base_price": data["base_price"],
                "fly_more_combo": data.get("fly_more_combo"),
                "fly_more_combo_plus": data.get("fly_more_combo_plus"),
                "care_refresh_1yr": data.get("care_refresh_1yr"),
                "care_refresh_2yr": data.get("care_refresh_2yr"),
                "url": v["url"],
            })
        return {
            "found": True,
            "display_name": data["display_name"],
            "base_price": data["base_price"],
            "fly_more_combo": data.get("fly_more_combo"),
            "fly_more_combo_plus": data.get("fly_more_combo_plus"),
            "care_refresh_1yr": data.get("care_refresh_1yr"),
            "care_refresh_2yr": data.get("care_refresh_2yr"),
            "vendors": vendor_list,
            "note": "These are MSRP prices. All authorized retailers sell at the same base price. Use web search to check for deals or sales.",
        }
    else:
        return {"found": False, "message": f"No reference data for '{drone_model}'"}


# ─────────────────────────────────────────────────────────────────────────────
# Tool definitions for OpenAI function calling
# ─────────────────────────────────────────────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_duckduckgo",
            "description": (
                "Execute a web search using DuckDuckGo. Use this to find current prices, "
                "product pages, or any information about DJI drones from retailers. "
                "DO NOT use 'site:' operators — they don't work reliably. Instead, "
                "include the retailer name in the query, e.g. 'DJI Air 3 price Amazon' "
                "or 'DJI Mini 4 Pro buy Best Buy price'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to execute (do NOT use site: operator)",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_prices",
            "description": (
                "Compare prices across multiple retailers. Provide a list of retailer data "
                "with names and prices. Returns the cheapest option, most expensive, "
                "average price, and potential savings."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "retailers_data": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "base_price": {"type": "number", "nullable": True},
                                "fly_more_combo": {"type": "number", "nullable": True},
                                "url": {"type": "string", "nullable": True},
                            },
                            "required": ["name"],
                        },
                        "description": "List of retailer pricing data to compare",
                    }
                },
                "required": ["retailers_data"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_stock_and_delivery",
            "description": (
                "Check stock availability and delivery estimates for a drone model "
                "across major retailers (DJI Store, Amazon, B&H Photo, Best Buy)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "drone_model": {
                        "type": "string",
                        "description": "Human-readable drone model name, e.g. 'DJI Mini 4 Pro'",
                    }
                },
                "required": ["drone_model"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_reference_pricing",
            "description": (
                "Get verified reference/baseline pricing from our internal database. "
                "ALWAYS call this tool first to get known prices, combo options, "
                "Care Refresh costs, and retailer URLs. Use web search only to "
                "supplement or verify this data."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "drone_model": {
                        "type": "string",
                        "description": "Drone model name, e.g. 'DJI Mini 4 Pro' or 'air_3'",
                    }
                },
                "required": ["drone_model"],
            },
        },
    },
]

# Map function names to implementations
TOOL_REGISTRY = {
    "search_duckduckgo": search_duckduckgo,
    "compare_prices": compare_prices,
    "check_stock_and_delivery": check_stock_and_delivery,
    "get_reference_pricing": get_reference_pricing,
}
