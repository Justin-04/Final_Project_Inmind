"""
MCP Tools: Document management — upload/ingest, list, delete.

Matches the proven working logic from the old API:
- List: scrolls Qdrant, counts chunks per source
- Delete: scrolls for matching source, deletes from Qdrant + S3
- Upload: extracts PDF, uploads images to S3, chunks, embeds, upserts
"""

import os
import base64
import logging
from typing import List, Dict, Any

import boto3
from botocore.exceptions import ClientError
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, FilterSelector

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "dji_manuals_parent_child")

# S3 config
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "final-project-inmind")
AWS_REGION = os.getenv("AWS_REGION", "eu-north-1")
S3_PREFIX = "images/"

s3_client = boto3.client(
    "s3",
    region_name=AWS_REGION,
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
)


def _get_qdrant() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL)


# ─────────────────────────────────────────────────────────────────────────────
# LIST DOCUMENTS
# ─────────────────────────────────────────────────────────────────────────────

def list_documents() -> List[Dict[str, Any]]:
    """
    List all unique ingested documents by scrolling the collection.

    Returns:
        list: [{"filename": str, "chunks": int}]
    """
    logger.info("list_documents: scrolling collection...")

    qdrant = _get_qdrant()
    source_counts = {}
    offset = None

    while True:
        results = qdrant.scroll(
            collection_name=COLLECTION_NAME,
            limit=100,
            offset=offset,
            with_payload=["source", "drone_model"],
            with_vectors=False,
        )
        points, next_offset = results

        for point in points:
            source = point.payload.get("source", "unknown")
            drone_model = point.payload.get("drone_model", "unknown")
            if source not in source_counts:
                source_counts[source] = {"chunks": 0, "drone_model": drone_model}
            source_counts[source]["chunks"] += 1

        if next_offset is None:
            break
        offset = next_offset

    documents = [
        {"filename": name, "drone_model": data["drone_model"], "chunks": data["chunks"]}
        for name, data in sorted(source_counts.items())
    ]
    logger.info(f"Found {len(documents)} unique documents")
    return documents


# ─────────────────────────────────────────────────────────────────────────────
# DELETE DOCUMENT
# ─────────────────────────────────────────────────────────────────────────────

def delete_document(source_name: str) -> Dict[str, Any]:
    """
    Delete all vectors for a document source from Qdrant + images from S3.

    Args:
        source_name: The source filename (e.g., "DJI_Air_3_User_Manual_v1.6_EN.pdf")

    Returns:
        {"status": str, "filename": str, "chunks_removed": int}
    """
    logger.info(f"delete_document: '{source_name}'")

    qdrant = _get_qdrant()

    # 1. Count matching points
    offset = None
    point_ids = []

    while True:
        results = qdrant.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=Filter(
                must=[FieldCondition(key="source", match=MatchValue(value=source_name))]
            ),
            limit=100,
            offset=offset,
            with_payload=False,
            with_vectors=False,
        )
        points, next_offset = results
        point_ids.extend([p.id for p in points])

        if next_offset is None:
            break
        offset = next_offset

    chunks_removed = len(point_ids)

    if chunks_removed == 0:
        return {
            "status": "not_found",
            "filename": source_name,
            "chunks_removed": 0,
            "message": f"Document '{source_name}' not found in vector store",
        }

    # 2. Delete from Qdrant
    qdrant.delete(
        collection_name=COLLECTION_NAME,
        points_selector=FilterSelector(
            filter=Filter(
                must=[FieldCondition(key="source", match=MatchValue(value=source_name))]
            )
        ),
    )

    # 3. Delete images from S3
    images_deleted = _delete_s3_images(source_name)

    logger.info(f"Deleted {chunks_removed} chunks + {images_deleted} S3 images for '{source_name}'")

    # Rebuild BM25 index after deletion
    try:
        from tools.retrieval import rebuild_bm25_index
        rebuild_bm25_index()
    except Exception as e:
        logger.warning(f"BM25 rebuild after delete failed: {e}")

    return {
        "status": "deleted",
        "filename": source_name,
        "chunks_removed": chunks_removed,
        "images_deleted": images_deleted,
    }


def _delete_s3_images(source_name: str) -> int:
    """Delete all S3 images matching the document stem."""
    doc_stem = source_name.replace(".pdf", "").replace(".PDF", "").replace(" ", "_")
    deleted = 0

    try:
        # List objects with matching prefix
        response = s3_client.list_objects_v2(
            Bucket=S3_BUCKET_NAME,
            Prefix=f"{S3_PREFIX}{doc_stem}",
        )

        objects = response.get("Contents", [])
        if not objects:
            return 0

        # Delete them
        delete_keys = [{"Key": obj["Key"]} for obj in objects]
        s3_client.delete_objects(
            Bucket=S3_BUCKET_NAME,
            Delete={"Objects": delete_keys},
        )
        deleted = len(delete_keys)
        logger.info(f"Deleted {deleted} images from S3 for '{doc_stem}'")

    except ClientError as e:
        logger.warning(f"S3 delete failed: {e}")

    return deleted


# ─────────────────────────────────────────────────────────────────────────────
# UPLOAD / INGEST
# ─────────────────────────────────────────────────────────────────────────────

def upload_and_ingest(file_bytes: bytes, filename: str, drone_model: str, caption_images: bool = False) -> Dict[str, Any]:
    """
    Full ingestion pipeline:
    1. Save PDF to temp file
    2. Extract text + images (upload to S3)
    3. Parent-child chunking
    4. Embed + upsert children to Qdrant

    Args:
        file_bytes: Raw PDF bytes
        filename: Original filename
        drone_model: Drone model label
        caption_images: Whether to caption images with GPT-4o Vision

    Returns:
        {"status": str, "filename": str, "pages": int, "chunks": int}
    """
    import tempfile
    logger.info(f"upload_and_ingest: '{filename}' (model: {drone_model})")

    try:
        from tools.extraction import extract_pdf
        from tools.ingestion import build_parent_child_chunks, get_embeddings, COLLECTION_NAME as ING_COLLECTION
        from qdrant_client.models import VectorParams, Distance, PointStruct

        # Step 1: Save bytes to temp file (extract_pdf needs a file path)
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        # Step 2: Extract pages (text + images → S3)
        # Use a temp images dir
        images_dir = os.path.join(tempfile.gettempdir(), "dji_images")
        os.makedirs(images_dir, exist_ok=True)

        pages = extract_pdf(
            pdf_path=tmp_path,
            doc_name=filename,
            images_dir=images_dir,
            caption_images=caption_images,
            upload_to_s3=True,
        )

        # Clean up temp PDF
        os.unlink(tmp_path)

        if not pages:
            return {"status": "error", "message": "No extractable content found in PDF"}

        # Add 'source' field required by ingestion chunking
        # Override drone_model detection with user-provided value
        for page in pages:
            page["source"] = filename
            page["drone_model_override"] = drone_model

        # Step 3: Parent-child chunking
        parents, children = build_parent_child_chunks(pages)

        if not children:
            return {"status": "error", "message": "No chunks created from PDF"}

        # Step 4: Embed + upsert to Qdrant
        qdrant = _get_qdrant()

        # Ensure collection exists
        if not qdrant.collection_exists(COLLECTION_NAME):
            qdrant.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
            )

        BATCH_SIZE = 64
        total_upserted = 0

        for batch_idx in range(0, len(children), BATCH_SIZE):
            batch = children[batch_idx:batch_idx + BATCH_SIZE]
            texts = [child["text"] for child in batch]
            embeddings = get_embeddings(texts)

            points = [
                PointStruct(
                    id=child["id"],
                    vector=embedding,
                    payload={
                        "text": child["text"],
                        "parent_text": child["parent_text"],
                        "parent_id": child["parent_id"],
                        **child["metadata"],
                    },
                )
                for child, embedding in zip(batch, embeddings)
            ]

            qdrant.upsert(collection_name=COLLECTION_NAME, points=points)
            total_upserted += len(points)

        logger.info(f"Ingested '{filename}': {len(pages)} pages, {total_upserted} chunks")

        # Rebuild BM25 index after ingestion
        try:
            from tools.retrieval import rebuild_bm25_index
            rebuild_bm25_index()
        except Exception as e:
            logger.warning(f"BM25 rebuild after ingest failed: {e}")

        return {
            "status": "ingested",
            "filename": filename,
            "pages": len(pages),
            "chunks": total_upserted,
        }

    except Exception as e:
        logger.error(f"Ingestion failed for '{filename}': {e}")
        return {"status": "error", "message": str(e)}
