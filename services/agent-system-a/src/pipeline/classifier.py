"""
Intent Classifier — Routes queries to the correct specialist agent.

Placeholder: keyword-based classification.
TODO: Replace with fine-tuned BERT model.

Intents:
- "rag"        → technical specs, features, how-to, manual content
- "diagnostic" → error codes, LED patterns, calibration failures
- "pricing"    → cost, purchase, vendors, deals, availability
"""

import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

DIAGNOSTIC_KEYWORDS = [
    "error", "code", "e00", "led", "blink", "flash", "esc",
    "calibrat", "fail", "problem", "issue", "not working",
    "warning", "beep", "crash", "motor", "obstacle",
]

PRICING_KEYWORDS = [
    "price", "cost", "buy", "purchase", "cheap", "expensive",
    "vendor", "store", "amazon", "best buy", "b&h", "dji store",
    "combo", "deal", "discount", "sale", "shipping", "in stock",
    "care refresh", "how much",
]

RAG_KEYWORDS = [
    "spec", "weight", "range", "speed", "battery", "camera",
    "sensor", "resolution", "how to", "manual", "feature",
    "max", "minimum", "distance", "altitude", "transmission",
    "gimbal", "fps", "video", "photo", "storage", "sd card",
    "controller", "remote", "pair", "connect", "update",
]


class IntentClassifier:
    """Keyword-based intent classifier (BERT placeholder)."""

    def classify(self, query: str, conversation_history: List[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Classify query intent using keywords + conversation context.

        Args:
            query: Current user query.
            conversation_history: Last N messages for context.

        Returns:
            {"intent": str, "confidence": float}
        """
        # Build full text from query + recent history
        history_text = ""
        if conversation_history:
            history_text = " ".join(
                m.get("content", "") for m in conversation_history[-4:]
            )

        full_text = f"{history_text} {query}".lower()

        # Score each intent
        diag_score = sum(1 for kw in DIAGNOSTIC_KEYWORDS if kw in full_text)
        price_score = sum(1 for kw in PRICING_KEYWORDS if kw in full_text)
        rag_score = sum(1 for kw in RAG_KEYWORDS if kw in full_text)

        # Pick highest scoring intent
        scores = {
            "diagnostic": diag_score,
            "pricing": price_score,
            "rag": rag_score,
        }

        best_intent = max(scores, key=scores.get)
        best_score = scores[best_intent]

        # If no keywords matched, default to RAG
        if best_score == 0:
            return {"intent": "rag", "confidence": 0.50}

        # Normalize confidence (rough heuristic)
        total = sum(scores.values())
        confidence = round(best_score / total, 2) if total > 0 else 0.50

        # Clamp confidence
        confidence = min(max(confidence, 0.50), 0.95)

        logger.info(f"Intent: {best_intent} (conf={confidence}, scores={scores})")
        return {"intent": best_intent, "confidence": confidence}
