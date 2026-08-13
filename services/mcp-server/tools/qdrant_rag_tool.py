"""
MCP Tool: query_dji_manual_vector_db

Wraps tools/retrieval.py — parent-child hybrid retrieval with:
- Dense vector search (OpenAI text-embedding-3-small)
- BM25 keyword search
- Redis semantic cache (15x speedup on repeated queries)
- Parent deduplication
- Reranking (BAAI/bge-reranker-base)

Returns top-k parent chunks with full context for the LLM.
"""

import logging
from typing import List, Dict, Any, Optional

from tools.retrieval import retrieve

logger = logging.getLogger(__name__)


def query_dji_manual_vector_db(
    query: str,
    drone_model: Optional[str] = None,
    top_k: int = 4,
    topic_filter: Optional[str] = None,
    modality_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Hybrid parent-child retrieval over DJI manual embeddings.

    Pipeline:
    1. Embed query → check Redis semantic cache
    2. If miss: dense vector search + BM25 over child chunks
    3. Deduplicate by parent (multiple children → same parent)
    4. Rerank parent texts with cross-encoder
    5. Return top-k parent chunks (1500 chars) with metadata

    Args:
        query: Natural language search query.
        drone_model: Filter by drone model (e.g., "DJI Mini 4 Pro"). Optional.
        top_k: Number of parent chunks to return (default: 4).
        topic_filter: Filter by topic. Optional.
        modality_filter: Filter by modality. Optional.

    Returns:
        list: Parent chunks with text, score, metadata (source, page, drone_model, image_paths).
    """
    logger.info(
        f"query_dji_manual_vector_db: query='{query[:60]}...', "
        f"drone={drone_model}, top_k={top_k}"
    )

    chunks = retrieve(
        query=query,
        top_k=top_k,
        drone_filter=drone_model,
        topic_filter=topic_filter,
        modality_filter=modality_filter,
        use_reranker=True,
        use_cache=True,
    )

    logger.info(f"Returned {len(chunks)} parent chunks")
    return chunks
