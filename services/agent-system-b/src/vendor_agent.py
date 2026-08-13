"""
Vendor Agent - DuckDuckGo-powered pricing and vendor breakdown service.

Uses DuckDuckGo Search (free, no API key) to look up real-time pricing
across major retailers:
  - Official DJI Store
  - Amazon
  - B&H Photo
  - Best Buy

Includes structured fallback data when web search is unavailable.
"""

import os
import re
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone

from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Fallback pricing data (used when web search fails or is rate-limited)
# ─────────────────────────────────────────────────────────────────────────────

FALLBACK_PRICING: Dict[str, Dict[str, Any]] = {
    "dji_mini_4_pro": {
        "display_name": "DJI Mini 4 Pro",
        "base_price": 759.00,
        "fly_more_combo": 959.00,
        "fly_more_combo_plus": 1099.00,
        "care_refresh_1yr": 79.00,
        "care_refresh_2yr": 129.00,
        "vendors": [
            {"name": "DJI Store", "url": "https://store.dji.com/product/dji-mini-4-pro"},
            {"name": "Amazon", "url": "https://www.amazon.com/dp/B0CHR5FZL4"},
            {"name": "B&H Photo", "url": "https://www.bhphotovideo.com/c/product/1790089-REG/"},
            {"name": "Best Buy", "url": "https://www.bestbuy.com/site/dji-mini-4-pro/6554899.p"},
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
            {"name": "Amazon", "url": "https://www.amazon.com/dp/B0C7GT7TT3"},
            {"name": "B&H Photo", "url": "https://www.bhphotovideo.com/c/product/1773178-REG/"},
            {"name": "Best Buy", "url": "https://www.bestbuy.com/site/dji-air-3/6544854.p"},
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
            {"name": "Amazon", "url": "https://www.amazon.com/dp/B0C1J6R7K8"},
            {"name": "B&H Photo", "url": "https://www.bhphotovideo.com/c/product/1757988-REG/"},
            {"name": "Best Buy", "url": "https://www.bestbuy.com/site/dji-mavic-3-pro/6535597.p"},
        ],
    },
}

# Model name normalization map
MODEL_ALIASES: Dict[str, str] = {
    "mini_4_pro": "dji_mini_4_pro",
    "mini 4 pro": "dji_mini_4_pro",
    "dji mini 4 pro": "dji_mini_4_pro",
    "air_3": "dji_air_3",
    "air 3": "dji_air_3",
    "dji air 3": "dji_air_3",
    "mavic_3_pro": "dji_mavic_3_pro",
    "mavic 3 pro": "dji_mavic_3_pro",
    "dji mavic 3 pro": "dji_mavic_3_pro",
}

# Retailers to search
RETAILERS = [
    {"name": "DJI Store", "site": "store.dji.com"},
    {"name": "Amazon", "site": "amazon.com"},
    {"name": "B&H Photo", "site": "bhphotovideo.com"},
    {"name": "Best Buy", "site": "bestbuy.com"},
]


class VendorAgent:
    """
    DuckDuckGo-powered vendor and pricing agent.

    Uses free DuckDuckGo search to retrieve live pricing
    from major DJI drone retailers. No API keys required.
    """

    def __init__(self):
        """Initialize the search client."""
        self.ddgs = DDGS()
        logger.info("VendorAgent initialized (DuckDuckGo search)")

    def _normalize_model(self, drone_model: str) -> str:
        """Normalize drone model string to internal key."""
        return MODEL_ALIASES.get(drone_model.lower().strip(), drone_model.lower().replace(" ", "_"))

    def _get_display_name(self, model_key: str) -> str:
        """Get human-readable display name from model key."""
        fallback = FALLBACK_PRICING.get(model_key)
        if fallback:
            return fallback["display_name"]
        return model_key.replace("_", " ").replace("dji ", "DJI ").title()

    async def get_pricing(
        self,
        drone_model: str,
        query: str,
        currency: str = "USD",
    ) -> Dict[str, Any]:
        """
        Get pricing breakdown for a drone model.

        Attempts live DuckDuckGo search; falls back to cached data if unavailable.

        Args:
            drone_model: Target drone model identifier
            query: User's pricing query for additional context
            currency: Currency code (default: USD)

        Returns:
            dict: Structured pricing response
        """
        model_key = self._normalize_model(drone_model)
        display_name = self._get_display_name(model_key)
        timestamp = datetime.now(timezone.utc).isoformat()

        # Attempt live DuckDuckGo search
        try:
            live_result = self._search_live_pricing(model_key, display_name, query)
            if live_result and any(v.get("base_price") for v in live_result):
                return {
                    "drone_model": model_key,
                    "display_name": display_name,
                    "source": "live_web_search",
                    "timestamp": timestamp,
                    "currency": currency,
                    "vendors": live_result,
                }
        except Exception as e:
            logger.warning(f"Live search failed, falling back: {e}")

        # Fallback to cached data
        return self._get_fallback_pricing(model_key, currency, timestamp)

    def _search_live_pricing(
        self,
        model_key: str,
        display_name: str,
        query: str,
    ) -> List[Dict[str, Any]]:
        """
        Use DuckDuckGo to search for live pricing per retailer.

        Args:
            model_key: Normalized model key
            display_name: Human-readable model name
            query: User query for context

        Returns:
            list: Vendor pricing entries
        """
        vendors = []

        for retailer in RETAILERS:
            vendor_entry = {
                "name": retailer["name"],
                "base_price": None,
                "fly_more_combo": None,
                "fly_more_combo_plus": None,
                "care_refresh_1yr": None,
                "care_refresh_2yr": None,
                "in_stock": None,
                "delivery_estimate": None,
                "url": None,
            }

            try:
                # Search DuckDuckGo for this retailer + drone model
                search_query = f"{display_name} price site:{retailer['site']}"
                results = self.ddgs.text(search_query, max_results=3)

                if results:
                    # Extract URL from first result
                    vendor_entry["url"] = results[0].get("href")

                    # Combine all snippet text for price extraction
                    combined_text = " ".join(
                        f"{r.get('title', '')} {r.get('body', '')}" for r in results
                    )

                    # Extract prices from snippets
                    prices = self._extract_prices(combined_text)
                    if prices:
                        vendor_entry["base_price"] = prices[0]
                    if len(prices) >= 2:
                        vendor_entry["fly_more_combo"] = prices[1]
                    if len(prices) >= 3:
                        vendor_entry["fly_more_combo_plus"] = prices[2]

                    # Check stock availability
                    text_lower = combined_text.lower()
                    if "in stock" in text_lower or "add to cart" in text_lower:
                        vendor_entry["in_stock"] = True
                    elif "out of stock" in text_lower or "sold out" in text_lower:
                        vendor_entry["in_stock"] = False

                    # Delivery estimate
                    delivery_match = re.search(
                        r'(\d+[-–]\d+\s*(?:business\s*)?days)', text_lower
                    )
                    if delivery_match:
                        vendor_entry["delivery_estimate"] = delivery_match.group(1)

            except Exception as e:
                logger.warning(f"Search failed for {retailer['name']}: {e}")

            vendors.append(vendor_entry)

        return vendors

    def _get_fallback_pricing(
        self,
        model_key: str,
        currency: str,
        timestamp: str,
    ) -> Dict[str, Any]:
        """
        Return cached fallback pricing when live search is unavailable.
        """
        data = FALLBACK_PRICING.get(model_key)

        if not data:
            return {
                "drone_model": model_key,
                "display_name": model_key.replace("_", " ").title(),
                "source": "fallback",
                "timestamp": timestamp,
                "currency": currency,
                "error": f"No pricing data available for model: {model_key}",
                "vendors": [],
            }

        vendors = []
        for vendor in data["vendors"]:
            vendors.append({
                "name": vendor["name"],
                "base_price": data["base_price"],
                "fly_more_combo": data.get("fly_more_combo"),
                "fly_more_combo_plus": data.get("fly_more_combo_plus"),
                "care_refresh_1yr": data.get("care_refresh_1yr"),
                "care_refresh_2yr": data.get("care_refresh_2yr"),
                "in_stock": None,
                "delivery_estimate": None,
                "url": vendor["url"],
            })

        return {
            "drone_model": model_key,
            "display_name": data["display_name"],
            "source": "fallback",
            "timestamp": timestamp,
            "currency": currency,
            "vendors": vendors,
        }

    @staticmethod
    def _extract_prices(text: str) -> List[float]:
        """
        Extract dollar amounts from text.

        Args:
            text: Raw text containing price mentions.

        Returns:
            list: Sorted unique prices found (ascending).
        """
        # Match patterns like $759, $759.00, $1,299.00
        matches = re.findall(r'\$[\d,]+\.?\d*', text)
        prices = []
        for match in matches:
            try:
                price = float(match.replace("$", "").replace(",", ""))
                if 10 < price < 10000:  # Reasonable drone price range
                    prices.append(price)
            except ValueError:
                continue

        # Remove duplicates and sort
        return sorted(set(prices))
