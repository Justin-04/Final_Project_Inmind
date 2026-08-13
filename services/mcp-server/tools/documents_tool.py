"""
MCP Tool: Document management (list and delete).

Lists unique ingested documents and deletes all vectors for a given source.
"""

import os
import logging
from typing import List, Dict, Any

from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

logger = logging.getLogger(__name__)

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "dji_manuals_parent_child")


def _get_client() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL)


def list_documents() -> List[Dict[str, Any]]:
    """
    List all unique ingested documents in the vector database.

    Scrolls through the collection and extracts unique source names
    with their drone_model and page count.

    Returns:
        list: [{"source": str, "drone_model": str, "chunk_count": int}]
    """
    logger.info("list_documents: scanning collection...")

    client = _get_client()

    # Scroll through all points and collect unique sources
    sources = {}
    offset = None
    batch_size = 100

    while True:
        results, offset = client.scroll(
            collection_name=COLLECTION_NAME,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )

        for point in results:
            payload = point.payload or {}
            source = payload.get("source", "unknown")
            drone_model = payload.get("drone_model", "unknown")

            if source not in sources:
                sources[source] = {
                    "source": source,
                    "drone_model": drone_model,
                    "chunk_count": 0,
                }
            sources[source]["chunk_count"] += 1

        if offset is None:
            break

    documents = list(sources.values())
    logger.info(f"Found {len(documents)} unique documents")
    return documents


def delete_document(source_name: str) -> Dict[str, Any]:
    """
    Delete all vectors belonging to a specific document source.

    Args:
        source_name: The source name to delete (e.g., "DJI_Air_3_User_Manual_v1.6_EN")

    Returns:
        {"deleted": bool, "source": str, "message": str}
    """
    logger.info(f"delete_document: deleting source='{source_name}'")

    client = _get_client()

    try:
        # Delete all points matching this source
        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="source",
                        match=MatchValue(value=source_name),
                    )
                ]
            ),
        )

        logger.info(f"Deleted all chunks for source: {source_name}")
        return {
            "deleted": True,
            "source": source_name,
            "message": f"All chunks for '{source_name}' deleted successfully",
        }

    except Exception as e:
        logger.error(f"Delete failed: {e}")
        return {
            "deleted": False,
            "source": source_name,
            "message": f"Delete failed: {str(e)}",
        }
