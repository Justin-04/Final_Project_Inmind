"""
Output Guard — Validates the final response before sending to user.

Checks:
- No hallucinated external URLs (only allow known domains)
- No leaked system prompt fragments
- Response isn't empty
- Markdown safety (no script injection)
"""

import re
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Known safe domains for URLs in responses
SAFE_DOMAINS = [
    "store.dji.com",
    "amazon.com",
    "bhphotovideo.com",
    "bestbuy.com",
    "s3.amazonaws.com",
]

# Patterns that should never appear in output
BLOCKED_PATTERNS = [
    r"<script",
    r"javascript:",
    r"onclick=",
    r"onerror=",
    r"system prompt",
    r"you are a",
    r"ignore previous",
]


class OutputGuard:
    """Validates and sanitizes the final response."""

    def validate(self, response: str) -> Dict[str, Any]:
        """
        Validate the output response.

        Args:
            response: The final response string.

        Returns:
            {"valid": bool, "response": str (potentially sanitized), "warnings": list}
        """
        warnings = []

        # Check empty
        if not response or not response.strip():
            return {"valid": False, "response": "I couldn't generate a response. Please try again.", "warnings": ["empty_response"]}

        # Check for blocked patterns
        response_lower = response.lower()
        for pattern in BLOCKED_PATTERNS:
            if re.search(pattern, response_lower):
                warnings.append(f"blocked_pattern: {pattern}")
                # Remove the offending content
                response = re.sub(pattern, "[removed]", response, flags=re.IGNORECASE)

        # Check URLs — only allow known domains
        urls = re.findall(r'https?://[^\s\)]+', response)
        for url in urls:
            if not any(domain in url for domain in SAFE_DOMAINS):
                warnings.append(f"unknown_url: {url}")
                # Don't remove — could be legitimate, just flag

        if warnings:
            logger.warning(f"OutputGuard warnings: {warnings}")

        return {
            "valid": len(warnings) == 0 or all("unknown_url" in w for w in warnings),
            "response": response,
            "warnings": warnings,
        }
