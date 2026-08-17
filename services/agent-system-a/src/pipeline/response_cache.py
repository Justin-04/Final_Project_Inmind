"""
Agent-Level Response Cache — Redis Semantic Cache.

Caches final responses by query embedding similarity.
If a similar query (cosine > 0.95) was answered before, return cached response instantly.

Placed AFTER input guard, BEFORE the rest of the pipeline.
"""

import os
import json
import logging
import hashlib
import numpy as np
from typing import Optional, Dict, Any

from openai import OpenAI

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6380")
CACHE_SIMILARITY_THRESHOLD = 0.92
CACHE_PREFIX = "agent_response_cache:"
EMBEDDING_MODEL = "text-embedding-3-small"

# Lazy Redis connection
_redis = None
_openai = None


def _get_redis():
    global _redis
    if _redis is not None:
        return _redis
    try:
        import redis
        _redis = redis.from_url(REDIS_URL, decode_responses=False)
        _redis.ping()
        logger.info("Response cache: Redis connected")
        return _redis
    except Exception as e:
        logger.warning(f"Response cache: Redis unavailable ({e})")
        return None


def _get_openai():
    global _openai
    if _openai is None:
        _openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _openai


def _embed_query(query: str) -> list:
    """Embed query for cache lookup."""
    client = _get_openai()
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=query)
    return response.data[0].embedding


def _cosine_similarity(a: list, b: list) -> float:
    """Compute cosine similarity between two vectors."""
    a_np = np.array(a, dtype=np.float32)
    b_np = np.array(b, dtype=np.float32)
    return float(np.dot(a_np, b_np) / (np.linalg.norm(a_np) * np.linalg.norm(b_np)))


class ResponseCache:
    """Agent-level semantic response cache."""

    def __init__(self):
        self.redis = _get_redis()
        self.available = self.redis is not None

    def lookup(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Check if a similar query has a cached response.

        Args:
            query: Current user query.

        Returns:
            Cached response dict if found (cosine > 0.95), None otherwise.
        """
        if not self.available:
            return None

        try:
            # Embed the query
            query_embedding = _embed_query(query)

            # Scan all cached entries (simple approach for small cache)
            keys = self.redis.keys(f"{CACHE_PREFIX}*")

            best_match = None
            best_score = 0.0

            for key in keys:
                raw = self.redis.get(key)
                if not raw:
                    continue

                entry = json.loads(raw)
                cached_embedding = entry.get("embedding")
                if not cached_embedding:
                    continue

                score = _cosine_similarity(query_embedding, cached_embedding)

                if score > best_score:
                    best_score = score
                    best_match = entry

            if best_score >= CACHE_SIMILARITY_THRESHOLD and best_match:
                logger.info(f"Response cache HIT (score={best_score:.3f}): {query[:50]}")
                return {
                    "response": best_match["response"],
                    "intent": best_match.get("intent", ""),
                    "metadata": best_match.get("metadata", {}),
                    "cache_hit": True,
                    "cache_score": best_score,
                }

            logger.debug(f"Response cache MISS (best={best_score:.3f}): {query[:50]}")
            return None

        except Exception as e:
            logger.warning(f"Response cache lookup error: {e}")
            return None

    def store(self, query: str, response: str, intent: str, metadata: dict):
        """
        Store a response in the cache.

        Args:
            query: The query that produced this response.
            response: The final response text.
            intent: Classified intent.
            metadata: Response metadata.
        """
        if not self.available:
            return

        try:
            query_embedding = _embed_query(query)

            # Generate a unique key based on query hash
            key = f"{CACHE_PREFIX}{hashlib.md5(query.encode()).hexdigest()}"

            entry = {
                "query": query,
                "embedding": query_embedding,
                "response": response,
                "intent": intent,
                "metadata": metadata,
            }

            # Store with 30s expiry (short for demo, use 86400 in production)
            self.redis.set(key, json.dumps(entry), ex=86400)
            logger.info(f"Response cache STORED: {query[:50]}")

        except Exception as e:
            logger.warning(f"Response cache store error: {e}")
