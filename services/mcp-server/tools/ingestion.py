"""
Parent-Child Chunking Ingestion.

Strategy:
- Parent chunks: 1500 chars (same as current best) — sent to the LLM as context
- Child chunks: 300 chars — embedded for precise vector matching
- Each child stores its parent_id so the retriever can expand to the full parent

The idea: small children embed precisely against queries, but the LLM sees
the larger parent for full context. Best of both worlds.

Collection: dji_manuals_parent_child (stores ONLY children with embeddings)
Parent text is stored in child payload as "parent_text" for retrieval-time expansion.

Usage:
    python -m ingestion.ingest_parent_child
"""

import os
import re
import uuid
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
)
from dotenv import load_dotenv

load_dotenv()

EXTRACTED_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "extracted_v2")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")

from tools.config import (
    COLLECTION_NAME,
    EMBEDDING_MODEL,
    EMBEDDING_DIM,
    PARENT_CHUNK_SIZE,
    PARENT_CHUNK_OVERLAP,
    CHILD_CHUNK_SIZE,
    CHILD_CHUNK_OVERLAP,
)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# ─── Page Loading ─────────────────────────────────────────────────────────────

def load_pages() -> list[dict]:
    """Load extracted .txt files and split into per-page sections."""
    pages = []

    for filename in sorted(os.listdir(EXTRACTED_DIR)):
        if not filename.endswith(".txt"):
            continue

        filepath = os.path.join(EXTRACTED_DIR, filename)
        manual_name = filename.replace(".txt", ".pdf")

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        page_parts = re.split(r"─{50}\n\[PAGE (\d+)\]\n─{50}", content)

        for i in range(1, len(page_parts), 2):
            page_num = int(page_parts[i])
            page_content = page_parts[i + 1].strip() if i + 1 < len(page_parts) else ""

            if not page_content or len(page_content) < 50:
                continue

            pages.append({
                "text": page_content,
                "source": manual_name,
                "page": page_num,
            })

    return pages


# ─── Chunking ─────────────────────────────────────────────────────────────────

def detect_drone_model(source: str) -> str:
    source_lower = source.lower()
    if "mavic" in source_lower and "classic" in source_lower:
        return "DJI Mavic 3 Classic"
    elif "mavic" in source_lower:
        return "DJI Mavic 3 Pro"
    elif "mini" in source_lower:
        return "DJI Mini 4 Pro"
    elif "air" in source_lower:
        return "DJI Air 3"
    elif "neo" in source_lower:
        return "DJI Neo"
    elif "avata" in source_lower:
        return "DJI Avata 2"
    elif "phantom" in source_lower:
        return "DJI Phantom"
    elif "inspire" in source_lower:
        return "DJI Inspire"
    return "Unknown"


def classify_modality(text: str) -> str:
    if "[CAPTION]" in text or "[IMAGE" in text or "[VISUAL" in text:
        return "image"
    spec_patterns = re.findall(
        r"\d+[\.\d]*\s*(m/s|mm|g|mAh|V|Wh|dBm|GHz|km|fps|MB/s|°|min|ms)", text
    )
    if len(spec_patterns) >= 3:
        return "table"
    return "text"


def detect_topic(text: str) -> str:
    text_lower = text.lower()
    topic_keywords = {
        "flight_modes": ["sport mode", "normal mode", "cine mode", "atti mode", "flight mode"],
        "battery": ["battery", "charging", "mah", "voltage", "hibernate"],
        "camera": ["camera", "gimbal", "aperture", "iso", "shutter", "video resolution"],
        "safety": ["do not", "warning", "caution", "restricted", "geo zone"],
        "remote_controller": ["remote controller", "control stick", "rc-n", "rc 2", "touchscreen"],
        "rth": ["return to home", "rth", "home point", "failsafe"],
        "obstacle_avoidance": ["vision system", "obstacle", "apas", "infrared", "sensing"],
        "intelligent_flight": ["quickshot", "mastershot", "hyperlapse", "waypoint", "focustrack"],
        "specs": ["specifications", "takeoff weight", "max ascent", "max horizontal"],
        "transmission": ["transmission", "o3+", "o4", "antenna", "frequency", "latency"],
    }
    for topic, keywords in topic_keywords.items():
        if any(kw in text_lower for kw in keywords):
            return topic
    return "general"


def create_parent_chunks(pages: list[dict]) -> list[dict]:
    """Create parent chunks using fixed-length sliding window (same as ingest_v2)."""
    parents = []

    for page in pages:
        text = page["text"]
        source = page["source"]
        page_num = page["page"]
        drone_model = page.get("drone_model_override") or detect_drone_model(source)

        start = 0
        chunk_index = 0

        while start < len(text):
            end = start + PARENT_CHUNK_SIZE
            chunk_text = text[start:end]

            # Try to break at sentence/paragraph boundary
            if end < len(text):
                last_break = max(chunk_text.rfind("\n"), chunk_text.rfind(". "))
                if last_break > PARENT_CHUNK_SIZE * 0.5:
                    end = start + last_break + 1
                    chunk_text = text[start:end]

            chunk_text = chunk_text.strip()
            if len(chunk_text) < 50:
                break

            image_paths = re.findall(r"\[IMAGE_PATH\]: (.+)", chunk_text)

            parent_id = str(uuid.uuid4())
            parents.append({
                "id": parent_id,
                "text": chunk_text,
                "metadata": {
                    "source": source,
                    "page": page_num,
                    "chunk_index": chunk_index,
                    "chunk_length": len(chunk_text),
                    "drone_model": drone_model,
                    "modality": classify_modality(chunk_text),
                    "topic": detect_topic(chunk_text),
                    "has_image_caption": "[CAPTION]" in chunk_text,
                    "image_paths": image_paths,
                },
            })

            chunk_index += 1
            start = end - PARENT_CHUNK_OVERLAP

    return parents


def create_child_chunks(parent: dict) -> list[dict]:
    """Split a parent chunk into smaller child chunks for precise embedding."""
    text = parent["text"]
    children = []
    start = 0
    child_index = 0

    while start < len(text):
        end = start + CHILD_CHUNK_SIZE
        child_text = text[start:end]

        # Try to break at sentence boundary
        if end < len(text):
            last_break = max(child_text.rfind(". "), child_text.rfind("\n"))
            if last_break > CHILD_CHUNK_SIZE * 0.4:
                end = start + last_break + 1
                child_text = text[start:end]

        child_text = child_text.strip()
        if len(child_text) < 30:
            break

        children.append({
            "id": str(uuid.uuid4()),
            "text": child_text,
            "parent_id": parent["id"],
            "parent_text": parent["text"],
            "child_index": child_index,
            "metadata": {
                **parent["metadata"],
                "chunk_type": "child",
                "parent_id": parent["id"],
                "child_index": child_index,
                "chunk_length": len(child_text),
            },
        })

        child_index += 1
        start = end - CHILD_CHUNK_OVERLAP

    return children


def build_parent_child_chunks(pages: list[dict]) -> tuple[list[dict], list[dict]]:
    """Create all parent and child chunks."""
    parents = create_parent_chunks(pages)
    all_children = []

    for parent in parents:
        children = create_child_chunks(parent)
        all_children.extend(children)

    return parents, all_children


# ─── Embedding & Ingestion ────────────────────────────────────────────────────

def get_embeddings(texts: list[str]) -> list[list[float]]:
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    return [item.embedding for item in response.data]


def ingest_to_qdrant(children: list[dict]):
    """
    Ingest CHILD chunks into Qdrant with embeddings.
    Parent text is stored in each child's payload for retrieval-time expansion.
    """
    qdrant = QdrantClient(url=QDRANT_URL)

    # Create collection only if it doesn't exist (preserve existing documents)
    if not qdrant.collection_exists(COLLECTION_NAME):
        qdrant.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=EMBEDDING_DIM,
                distance=Distance.COSINE,
            ),
        )
        print(f"  Created collection '{COLLECTION_NAME}' (dim={EMBEDDING_DIM}, cosine)")
    else:
        print(f"  Using existing collection '{COLLECTION_NAME}'")

    BATCH_SIZE = 64
    total_batches = (len(children) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_idx in range(0, len(children), BATCH_SIZE):
        batch = children[batch_idx:batch_idx + BATCH_SIZE]
        batch_num = batch_idx // BATCH_SIZE + 1

        print(f"  Embedding & upserting batch {batch_num}/{total_batches} "
              f"({len(batch)} children)...")

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

    return qdrant


# ─── Entry Point ──────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("PARENT-CHILD CHUNKING INGESTION")
    print("=" * 60)
    print(f"  Parent size: {PARENT_CHUNK_SIZE} chars (overlap {PARENT_CHUNK_OVERLAP})")
    print(f"  Child size: {CHILD_CHUNK_SIZE} chars (overlap {CHILD_CHUNK_OVERLAP})")

    # Step 1: Load pages
    print("\n[1/4] Loading extracted documents...")
    pages = load_pages()
    print(f"  Loaded {len(pages)} pages from "
          f"{len(set(p['source'] for p in pages))} manuals")

    # Step 2: Create parent + child chunks
    print("\n[2/4] Creating parent-child chunks...")
    parents, children = build_parent_child_chunks(pages)
    print(f"  Parents: {len(parents)}")
    print(f"  Children: {len(children)}")
    print(f"  Avg children per parent: {len(children) / len(parents):.1f}")

    # Stats
    parent_sizes = [p["metadata"]["chunk_length"] for p in parents]
    child_sizes = [c["metadata"]["chunk_length"] for c in children]
    print(f"\n  Parent chunk sizes: min={min(parent_sizes)}, max={max(parent_sizes)}, "
          f"avg={sum(parent_sizes)//len(parent_sizes)}")
    print(f"  Child chunk sizes: min={min(child_sizes)}, max={max(child_sizes)}, "
          f"avg={sum(child_sizes)//len(child_sizes)}")

    # Per manual
    sources = {}
    for child in children:
        src = child["metadata"]["source"]
        sources[src] = sources.get(src, 0) + 1
    print(f"\n  Children per manual:")
    for src, count in sorted(sources.items()):
        print(f"    {src}: {count}")

    # Step 3: Ingest children into Qdrant
    print("\n[3/4] Embedding and ingesting children into Qdrant...")
    qdrant = ingest_to_qdrant(children)

    info = qdrant.get_collection(COLLECTION_NAME)
    print(f"\n  Collection '{COLLECTION_NAME}': {info.points_count} points indexed")

    # Step 4: Summary
    print(f"\n[4/4] Summary")
    print(f"  Search happens on: child chunks ({CHILD_CHUNK_SIZE} chars)")
    print(f"  LLM receives: parent chunks ({PARENT_CHUNK_SIZE} chars)")
    print(f"  Retriever must use 'parent_text' from payload for context")

    print(f"\n{'='*60}")
    print("Done! Parent-child chunks ready for retrieval.")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
