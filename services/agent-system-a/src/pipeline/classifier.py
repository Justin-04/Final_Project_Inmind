"""
Intent Classifier — Fine-tuned DistilBERT.

Classifies queries into: rag, diagnostic, pricing
Model: models/bert_intent_classifier/model/

Falls back to keyword-based classification if model isn't available.
"""

import os
import logging
from typing import Dict, Any, List
from pathlib import Path

logger = logging.getLogger(__name__)

# Model path — from env or relative to project root
MODEL_PATH = Path(os.getenv("BERT_MODEL_PATH", str(Path(__file__).parent.parent.parent.parent / "models" / "bert_intent_classifier" / "model")))

# Lazy-loaded model
_model = None
_tokenizer = None
_labels = {0: "rag", 1: "diagnostic", 2: "pricing"}


def _load_model():
    """Load the fine-tuned BERT model (once)."""
    global _model, _tokenizer

    if _model is not None:
        return True

    if not MODEL_PATH.exists():
        logger.warning(f"BERT model not found at {MODEL_PATH} — using fallback")
        return False

    try:
        from transformers import DistilBertForSequenceClassification, DistilBertTokenizer
        import torch

        logger.info(f"Loading BERT classifier from {MODEL_PATH}...")
        _tokenizer = DistilBertTokenizer.from_pretrained(str(MODEL_PATH))
        _model = DistilBertForSequenceClassification.from_pretrained(str(MODEL_PATH))
        _model.eval()
        logger.info("BERT classifier loaded ✓")
        return True

    except Exception as e:
        logger.error(f"Failed to load BERT model: {e}")
        return False


class IntentClassifier:
    """Fine-tuned BERT intent classifier with keyword fallback."""

    def __init__(self):
        self.bert_available = _load_model()

    def classify(self, query: str, conversation_history: List[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Classify query intent.

        Uses BERT if available (fast, ~50ms).
        Falls back to keyword matching otherwise.

        Args:
            query: User's question.
            conversation_history: Recent messages for context.

        Returns:
            {"intent": str, "confidence": float, "method": "bert" | "keyword"}
        """
        if self.bert_available:
            result = self._classify_bert(query)
            # Post-processing: fix known BERT misclassifications
            result = self._apply_overrides(query, result)
            return result
        else:
            return self._classify_keywords(query, conversation_history)

    def _apply_overrides(self, query: str, bert_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Override BERT predictions when strong signal words are present.
        This fixes known edge cases (e.g., Neo queries misclassified as diagnostic).
        """
        text = query.lower()

        # Strong RAG indicators (specs, capabilities, features)
        strong_rag_patterns = [
            "what is the", "how far", "how fast", "how long", "how heavy",
            "max speed", "max range", "max altitude", "max flight time",
            "battery life", "flight time", "transmission range",
            "camera", "video resolution", "photo", "sensor",
            "weight", "dimensions", "specifications", "specs",
            "does it support", "does it have", "can it",
        ]

        # Strong pricing indicators
        strong_pricing_patterns = [
            "how much", "price", "cost", "buy", "purchase",
            "where to buy", "cheapest", "deal", "discount",
            "amazon", "best buy", "combo", "fly more",
        ]

        # Strong diagnostic indicators
        strong_diagnostic_patterns = [
            "error", "code e0", "not working", "won't", "failed",
            "crash", "problem", "troubleshoot", "fix",
            "blinking", "warning", "calibration failed",
        ]

        # Check for strong RAG patterns
        if any(pattern in text for pattern in strong_rag_patterns):
            # Don't override diagnostic if there's also an error indicator
            if not any(pattern in text for pattern in strong_diagnostic_patterns):
                return {"intent": "rag", "confidence": 0.95, "method": "bert+override"}

        # Check for strong pricing patterns
        if any(pattern in text for pattern in strong_pricing_patterns):
            return {"intent": "pricing", "confidence": 0.95, "method": "bert+override"}

        # Check for strong diagnostic patterns
        if any(pattern in text for pattern in strong_diagnostic_patterns):
            return {"intent": "diagnostic", "confidence": 0.95, "method": "bert+override"}

        # No override needed
        return bert_result

    def _classify_bert(self, query: str) -> Dict[str, Any]:
        """Classify using fine-tuned BERT."""
        import torch

        inputs = _tokenizer(
            query,
            padding="max_length",
            truncation=True,
            max_length=128,
            return_tensors="pt",
        )

        with torch.no_grad():
            outputs = _model(**inputs)
            logits = outputs.logits
            probs = torch.softmax(logits, dim=-1)
            confidence, predicted = torch.max(probs, dim=-1)

        intent = _labels[predicted.item()]
        conf = round(confidence.item(), 3)

        logger.info(f"BERT: {intent} (conf={conf})")
        return {"intent": intent, "confidence": conf, "method": "bert"}

    def _classify_keywords(self, query: str, history: List[Dict[str, str]] = None) -> Dict[str, Any]:
        """Fallback keyword-based classification."""
        text = query.lower()
        if history:
            text += " " + " ".join(m.get("content", "").lower() for m in history[-2:])

        # Strong indicators for each category
        diag_kw = ["error", "code", "e00", "led", "blink", "fail", "calibrat", "problem", "not working", "crash", "won't", "warning"]
        price_kw = ["price", "cost", "buy", "purchase", "cheap", "store", "amazon", "combo", "deal", "how much", "where to buy", "shipping"]
        rag_kw = ["spec", "weight", "range", "speed", "battery", "camera", "how to", "manual", "feature", "max", "what is", "does", "support"]

        d = sum(1 for kw in diag_kw if kw in text)
        p = sum(1 for kw in price_kw if kw in text)
        r = sum(1 for kw in rag_kw if kw in text)

        # Boost RAG for specification queries (common pattern)
        if any(word in text for word in ["max", "what is", "does", "how far", "flight time", "sensor", "video", "photo", "resolution"]):
            r += 2

        if d > p and d > r:
            return {"intent": "diagnostic", "confidence": 0.70, "method": "keyword"}
        elif p > d and p > r:
            return {"intent": "pricing", "confidence": 0.70, "method": "keyword"}
        else:
            return {"intent": "rag", "confidence": 0.60, "method": "keyword"}
