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
            return self._classify_bert(query)
        else:
            return self._classify_keywords(query, conversation_history)

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

        diag_kw = ["error", "code", "e00", "led", "blink", "fail", "calibrat", "problem", "not working"]
        price_kw = ["price", "cost", "buy", "purchase", "cheap", "store", "amazon", "combo", "deal", "how much"]
        rag_kw = ["spec", "weight", "range", "speed", "battery", "camera", "how to", "manual", "feature", "max"]

        d = sum(1 for kw in diag_kw if kw in text)
        p = sum(1 for kw in price_kw if kw in text)
        r = sum(1 for kw in rag_kw if kw in text)

        if d > p and d > r:
            return {"intent": "diagnostic", "confidence": 0.70, "method": "keyword"}
        elif p > d and p > r:
            return {"intent": "pricing", "confidence": 0.70, "method": "keyword"}
        else:
            return {"intent": "rag", "confidence": 0.60, "method": "keyword"}
