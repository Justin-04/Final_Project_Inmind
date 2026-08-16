"""
Input Guard V2 — Llama Prompt Guard 2 (22M params).

Uses meta-llama/Llama-Prompt-Guard-2-22M for fast, local
prompt injection and jailbreak detection.

No API calls needed — runs entirely on local CPU/GPU.
~50ms inference time vs ~2s for the LLM-based guard.

Labels:
- BENIGN: safe query
- INJECTION: prompt injection attempt
- JAILBREAK: jailbreak attempt
"""

import os
import logging
from typing import Dict, Any
from pathlib import Path

import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

logger = logging.getLogger(__name__)

MODEL_ID = "meta-llama/Llama-Prompt-Guard-2-22M"

# Lazy-loaded model
_model = None
_tokenizer = None


def _load_model():
    """Load Prompt Guard model (once)."""
    global _model, _tokenizer

    if _model is not None:
        return True

    try:
        logger.info(f"Loading Prompt Guard: {MODEL_ID}...")
        _tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
        _model = AutoModelForSequenceClassification.from_pretrained(MODEL_ID)
        _model.eval()
        logger.info("Prompt Guard loaded ✓")
        return True
    except Exception as e:
        logger.error(f"Failed to load Prompt Guard: {e}")
        return False


class InputGuardV2:
    """
    Llama Prompt Guard 2 — local model for injection/jailbreak detection.

    Faster and free compared to LLM-based guard.
    Falls back to LLM guard if model can't be loaded.
    """

    def __init__(self):
        self.model_available = _load_model()
        if not self.model_available:
            logger.warning("Prompt Guard not available — will fall back to LLM guard")

    def check(self, query: str) -> Dict[str, Any]:
        """
        Check if the user query is safe.

        Args:
            query: User's raw input.

        Returns:
            {"safe": bool, "reason": str or None, "label": str, "scores": dict}
        """
        if not self.model_available:
            # Fall back to simple heuristic
            return self._fallback_check(query)

        try:
            inputs = _tokenizer(
                query,
                return_tensors="pt",
                truncation=True,
                max_length=512,
            )

            with torch.no_grad():
                outputs = _model(**inputs)
                logits = outputs.logits
                probs = torch.softmax(logits, dim=-1)

            # Labels: 0=BENIGN, 1=INJECTION, 2=JAILBREAK
            scores = {
                "benign": round(probs[0][0].item(), 4),
                "injection": round(probs[0][1].item(), 4),
                "jailbreak": round(probs[0][2].item(), 4),
            }

            predicted = torch.argmax(probs, dim=-1).item()
            labels = {0: "benign", 1: "injection", 2: "jailbreak"}
            label = labels[predicted]

            is_safe = label == "benign"
            reason = None
            if not is_safe:
                reason = f"Detected: {label} (confidence: {max(scores['injection'], scores['jailbreak']):.2%})"

            logger.info(f"Prompt Guard: {label} (scores: {scores})")

            return {
                "safe": is_safe,
                "reason": reason,
                "label": label,
                "scores": scores,
            }

        except Exception as e:
            logger.warning(f"Prompt Guard error: {e} — defaulting to safe")
            return {"safe": True, "reason": None, "label": "error", "scores": {}}

    def _fallback_check(self, query: str) -> Dict[str, Any]:
        """Simple keyword fallback if model isn't available."""
        suspicious = [
            "ignore previous", "ignore all", "system prompt",
            "you are now", "DAN mode", "jailbreak",
            "disregard instructions", "bypass", "pretend you",
        ]
        query_lower = query.lower()
        for pattern in suspicious:
            if pattern in query_lower:
                return {
                    "safe": False,
                    "reason": f"Keyword match: '{pattern}'",
                    "label": "injection",
                    "scores": {},
                }
        return {"safe": True, "reason": None, "label": "benign", "scores": {}}
