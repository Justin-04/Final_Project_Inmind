"""
Parent-Child Retriever with Hybrid Search + Redis Semantic Cache.

Search: embed query → check Redis cache → if miss, match against child chunks
Expand: retrieve parent_text from matched children (1500 chars, full context)
Dedup: if multiple children point to the same parent, keep only the best-scoring one
Rerank: score query against parent texts, return top_k parents to LLM
Cache: store query embedding + results in Redis for future hits
"""

import os
import re
import json
import hashlib
import numpy as np

os.environ["USE_TF"] = "0"

from openai import OpenAI
from qdrant_client import QdrantClient, models
from qdrant_client.models import Filter, FieldCondition, MatchValue
from sentence_transformers import CrossEncoder
from rank_bm25 import BM25Okapi
from dotenv import load_dotenv
import redis
from redis.commands.search.field import VectorField, TextField, NumericField
from redis.commands.search.index_definition import IndexDefinition, IndexType
from redis.commands.search.query import Query

load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6380")
COLLECTION_NAME = "dji_manuals_parent_child"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536
LLM_MODEL = "gpt-4o-mini"
TOP_K = 4
RETRIEVAL_K = 30  # More candidates since children are smaller

# Cache config
CACHE_INDEX_NAME = "query_cache"
CACHE_SIMILARITY_THRESHOLD = 0.90  # Cosine similarity threshold for cache hit
CACHE_TTL = 86400  # No expiry for static manuals (set to seconds if needed)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
qdrant = QdrantClient(url=QDRANT_URL)

print("Loading reranker model...")
reranker = CrossEncoder("BAAI/bge-reranker-base")
print("Reranker loaded ✓")


# ─── Redis Semantic Cache ─────────────────────────────────────────────────────

def init_redis_cache():
    """Initialize Redis connection and create vector index if not exists."""
    try:
        r = redis.from_url(REDIS_URL, decode_responses=False)
        r.ping()
        print(f"Redis connected ✓ ({REDIS_URL})")
    except (redis.ConnectionError, redis.exceptions.ConnectionError):
        print("⚠ Redis not available — caching disabled")
        return None

    # Create index if it doesn't exist
    try:
        r.ft(CACHE_INDEX_NAME).info()
    except redis.exceptions.ResponseError:
        # Index doesn't exist — create it
        schema = (
            TextField("query"),
            TextField("answer"),
            TextField("chunks_json"),
            NumericField("timestamp"),
            VectorField(
                "embedding",
                "HNSW",
                {
                    "TYPE": "FLOAT32",
                    "DIM": EMBEDDING_DIM,
                    "DISTANCE_METRIC": "COSINE",
                },
            ),
        )
        r.ft(CACHE_INDEX_NAME).create_index(
            schema,
            definition=IndexDefinition(prefix=["cache:"], index_type=IndexType.HASH),
        )
        print(f"  Created Redis index '{CACHE_INDEX_NAME}'")

    return r


redis_client = init_redis_cache()


def cache_lookup(query_embedding: list[float]) -> dict | None:
    """
    Search Redis for a semantically similar cached query.
    Returns cached result if similarity > threshold, else None.
    """
    if redis_client is None:
        return None

    try:
        embedding_bytes = np.array(query_embedding, dtype=np.float32).tobytes()

        q = (
            Query(f"*=>[KNN 1 @embedding $vec AS score]")
            .sort_by("score")
            .return_fields("query", "answer", "chunks_json", "score")
            .dialect(2)
        )

        results = redis_client.ft(CACHE_INDEX_NAME).search(
            q, query_params={"vec": embedding_bytes}
        )

        if results.total == 0:
            return None

        hit = results.docs[0]
        # Redis COSINE distance: 0 = identical, 2 = opposite
        # Convert to similarity: 1 - distance
        distance = float(hit.score)
        similarity = 1 - distance

        if similarity >= CACHE_SIMILARITY_THRESHOLD:
            cached_query = hit.query.decode() if isinstance(hit.query, bytes) else hit.query
            cached_answer = hit.answer.decode() if isinstance(hit.answer, bytes) else hit.answer
            chunks_raw = hit.chunks_json.decode() if isinstance(hit.chunks_json, bytes) else hit.chunks_json
            cached_chunks = json.loads(chunks_raw)

            print(f"  ⚡ CACHE HIT (similarity: {similarity:.4f}) — query: \"{cached_query[:60]}...\"")
            return {
                "answer": cached_answer,
                "chunks": cached_chunks,
                "cache_hit": True,
                "similarity": similarity,
            }

    except Exception as e:
        print(f"  ⚠ Cache lookup error: {e}")

    return None


def cache_store(query: str, query_embedding: list[float], answer: str, chunks: list[dict]):
    """Store a query + answer in the Redis cache."""
    if redis_client is None:
        return

    try:
        # Create a deterministic key from the query
        key = f"cache:{hashlib.sha256(query.encode()).hexdigest()[:16]}"

        embedding_bytes = np.array(query_embedding, dtype=np.float32).tobytes()

        # Serialize chunks (only text + metadata, not full payload)
        chunks_serializable = []
        for chunk in chunks:
            chunks_serializable.append({
                "text": chunk["text"],
                "score": chunk.get("score", 0),
                "rerank_score": chunk.get("rerank_score", 0),
                "metadata": chunk["metadata"],
            })

        mapping = {
            "query": query,
            "answer": answer,
            "chunks_json": json.dumps(chunks_serializable, ensure_ascii=False),
            "embedding": embedding_bytes,
            "timestamp": int(__import__("time").time()),
        }

        redis_client.hset(key, mapping=mapping)

        if CACHE_TTL:
            redis_client.expire(key, CACHE_TTL)

    except Exception as e:
        print(f"  ⚠ Cache store error: {e}")


def cache_clear():
    """Clear all cached queries (call after re-ingestion)."""
    if redis_client is None:
        return

    try:
        redis_client.ft(CACHE_INDEX_NAME).dropindex(delete_documents=True)
        print("  Cache cleared ✓")
    except Exception:
        pass


# ─── BM25 Index ───────────────────────────────────────────────────────────────

def build_bm25_index():
    """Build BM25 index over child chunk texts."""
    print("Building BM25 index from parent-child collection...")

    all_docs = []
    offset = None

    while True:
        results = qdrant.scroll(
            collection_name=COLLECTION_NAME,
            limit=100,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )

        points, next_offset = results

        for point in points:
            all_docs.append({
                "id": point.id,
                "text": point.payload.get("text", ""),
                "parent_text": point.payload.get("parent_text", ""),
                "parent_id": point.payload.get("parent_id", ""),
                "metadata": {
                    "source": point.payload.get("source", ""),
                    "page": point.payload.get("page", 0),
                    "drone_model": point.payload.get("drone_model", ""),
                    "modality": point.payload.get("modality", ""),
                    "topic": point.payload.get("topic", ""),
                    "has_image_caption": point.payload.get("has_image_caption", False),
                    "image_paths": point.payload.get("image_paths", []),
                },
            })

        if next_offset is None:
            break
        offset = next_offset

    tokenized_corpus = [tokenize(doc["text"]) for doc in all_docs]
    bm25 = BM25Okapi(tokenized_corpus)

    print(f"BM25 index built: {len(all_docs)} child documents")
    return bm25, all_docs


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", text.lower())
    return [t for t in tokens if len(t) > 1]


bm25_index, bm25_docs = build_bm25_index()


# ─── Retrieval ────────────────────────────────────────────────────────────────

def embed_query(query: str) -> list[float]:
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=query)
    return response.data[0].embedding


def retrieve_semantic(query: str, query_embedding: list[float], top_k: int = RETRIEVAL_K) -> list[dict]:
    """Retrieve child chunks via dense vector search."""
    results = qdrant.query_points(
        collection_name=COLLECTION_NAME,
        query=query_embedding,
        limit=top_k,
        with_payload=True,
    )

    retrieved = []
    for hit in results.points:
        retrieved.append({
            "child_text": hit.payload.get("text", ""),
            "parent_text": hit.payload.get("parent_text", ""),
            "parent_id": hit.payload.get("parent_id", ""),
            "score": hit.score,
            "source": "semantic",
            "metadata": {
                "source": hit.payload.get("source", ""),
                "page": hit.payload.get("page", 0),
                "drone_model": hit.payload.get("drone_model", ""),
                "modality": hit.payload.get("modality", ""),
                "topic": hit.payload.get("topic", ""),
                "has_image_caption": hit.payload.get("has_image_caption", False),
                "image_paths": hit.payload.get("image_paths", []),
            },
        })

    return retrieved


def retrieve_bm25(query: str, top_k: int = RETRIEVAL_K) -> list[dict]:
    """Retrieve child chunks via BM25 keyword search."""
    tokenized_query = tokenize(query)
    scores = bm25_index.get_scores(tokenized_query)

    top_indices = scores.argsort()[-top_k:][::-1]

    retrieved = []
    for idx in top_indices:
        if scores[idx] > 0:
            doc = bm25_docs[idx]
            retrieved.append({
                "child_text": doc["text"],
                "parent_text": doc["parent_text"],
                "parent_id": doc["parent_id"],
                "score": float(scores[idx]),
                "source": "bm25",
                "metadata": doc["metadata"],
            })

    return retrieved


def deduplicate_by_parent(chunks: list[dict]) -> list[dict]:
    """
    If multiple children point to the same parent, keep only the
    highest-scoring child. This prevents sending the same parent
    text to the LLM multiple times.
    """
    best_per_parent = {}

    for chunk in chunks:
        parent_id = chunk["parent_id"]
        if parent_id not in best_per_parent:
            best_per_parent[parent_id] = chunk
        else:
            # Keep the one with higher score
            if chunk.get("score", 0) > best_per_parent[parent_id].get("score", 0):
                best_per_parent[parent_id] = chunk

    return list(best_per_parent.values())


def rerank(query: str, chunks: list[dict], top_k: int = TOP_K) -> list[dict]:
    """Rerank based on query vs PARENT text (what the LLM will see)."""
    if not chunks:
        return chunks

    # Rerank against parent text — that's what matters for answer quality
    pairs = [(query, chunk["parent_text"]) for chunk in chunks]
    scores = reranker.predict(pairs)

    for chunk, score in zip(chunks, scores):
        chunk["rerank_score"] = float(score)

    reranked = sorted(chunks, key=lambda x: x["rerank_score"], reverse=True)
    return reranked[:top_k]


def retrieve(
    query: str,
    top_k: int = TOP_K,
    drone_filter: str | None = None,
    topic_filter: str | None = None,
    modality_filter: str | None = None,
    use_reranker: bool = True,
    use_cache: bool = True,
) -> list[dict]:
    """
    Hybrid parent-child retrieval with Redis semantic cache:
    0. Embed query
    1. Check Redis cache for similar past queries
    2. If cache miss: get children from semantic + BM25
    3. Deduplicate by parent_id
    4. Apply metadata filters
    5. Rerank against parent text
    6. Store result in cache
    7. Return top_k with parent_text as the context
    """
    # Step 0: Embed query (needed for both cache check and retrieval)
    query_embedding = embed_query(query)

    # Step 1: Check cache (only for unfiltered queries — filters change results)
    if use_cache and not (drone_filter or topic_filter or modality_filter):
        cached = cache_lookup(query_embedding)
        if cached:
            return cached["chunks"]

    # Step 2: Full retrieval pipeline
    semantic_results = retrieve_semantic(query, query_embedding, top_k=RETRIEVAL_K)
    bm25_results = retrieve_bm25(query, top_k=RETRIEVAL_K)

    # Merge and deduplicate by child text
    seen_texts = set()
    merged = []

    for chunk in semantic_results + bm25_results:
        text_key = chunk["child_text"][:100]
        if text_key in seen_texts:
            continue
        seen_texts.add(text_key)

        # Apply filters
        if drone_filter and chunk["metadata"].get("drone_model") != drone_filter:
            continue
        if topic_filter and chunk["metadata"].get("topic") != topic_filter:
            continue
        if modality_filter and chunk["metadata"].get("modality") != modality_filter:
            continue

        merged.append(chunk)

    # Deduplicate by parent — don't send same parent twice
    merged = deduplicate_by_parent(merged)

    if use_reranker and merged:
        final = rerank(query, merged, top_k=top_k)
    else:
        final = merged[:top_k]

    # Convert to standard output format (text = parent_text for LLM)
    output = []
    for chunk in final:
        output.append({
            "text": chunk["parent_text"],  # LLM sees parent
            "score": chunk.get("score", 0),
            "rerank_score": chunk.get("rerank_score", 0),
            "metadata": chunk["metadata"],
        })

    # Step 6: Store in cache for future queries
    if use_cache and not (drone_filter or topic_filter or modality_filter):
        # Generate answer to cache alongside chunks
        # (We cache chunks only — answer is generated fresh or cached separately)
        cache_store(query, query_embedding, "", output)

    return output


# ─── Generation ───────────────────────────────────────────────────────────────

def generate_answer(query: str, context_chunks: list[dict]) -> str:
    context_parts = []
    for i, chunk in enumerate(context_chunks, 1):
        meta = chunk["metadata"]
        header = (
            f"[Source: {meta['source']}, Page {meta['page']}, "
            f"Drone: {meta['drone_model']}]"
        )
        score = chunk.get("rerank_score", chunk.get("score", 0))
        context_parts.append(
            f"--- Context {i} (score: {score:.3f}) ---\n{header}\n{chunk['text']}"
        )

    context_str = "\n\n".join(context_parts)

    system_prompt = """You are a knowledgeable DJI drone technical assistant. Answer questions 
accurately based ONLY on the provided context from DJI drone user manuals.

Rules:
- Use only information from the provided context chunks to answer.
- If the context doesn't contain enough information to fully answer, say so explicitly.
- Cite the source manual and page number when providing specific facts.
- Be concise and direct. Provide exact values when available.
- If the question asks about a diagram or image, use the [CAPTION] information from the context."""

    user_prompt = f"""Context from DJI drone manuals:

{context_str}

---

Question: {query}

Answer:"""

    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        max_tokens=500,
    )

    return response.choices[0].message.content.strip()


# ─── Full Pipeline with Answer Caching ────────────────────────────────────────

def query_with_cache(
    query: str,
    top_k: int = TOP_K,
    drone_filter: str | None = None,
    topic_filter: str | None = None,
    modality_filter: str | None = None,
) -> dict:
    """
    Full RAG pipeline with answer-level caching.
    On cache hit: skips retrieval + generation entirely (~0.3s).
    On cache miss: runs full pipeline, caches answer for next time.
    """
    # Check cache first (only for unfiltered queries)
    if not (drone_filter or topic_filter or modality_filter):
        query_embedding = embed_query(query)
        cached = cache_lookup(query_embedding)
        if cached:
            return {
                "answer": cached["answer"],
                "chunks": cached["chunks"],
                "cache_hit": True,
            }
    else:
        query_embedding = None

    # Cache miss — run full pipeline
    chunks = retrieve(
        query, top_k=top_k,
        drone_filter=drone_filter,
        topic_filter=topic_filter,
        modality_filter=modality_filter,
        use_cache=False,  # Don't double-cache
    )
    answer = generate_answer(query, chunks)

    # Store in cache (answer + chunks)
    if not (drone_filter or topic_filter or modality_filter):
        if query_embedding is None:
            query_embedding = embed_query(query)
        cache_store(query, query_embedding, answer, chunks)

    return {
        "answer": answer,
        "chunks": chunks,
        "cache_hit": False,
    }


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("DJI Drone Manual — Parent-Child Hybrid RAG")
    print("=" * 60)
    print("Search: child chunks (300 chars) | Context: parent chunks (1500 chars)")
    print("Type 'quit' to exit.\n")

    while True:
        question = input("Q: ").strip()
        if not question or question.lower() in ("quit", "exit", "q"):
            break

        chunks = retrieve(question, top_k=TOP_K)

        print(f"\n  Retrieved {len(chunks)} parent chunks:")
        for i, c in enumerate(chunks, 1):
            meta = c["metadata"]
            score = c.get("rerank_score", c.get("score", 0))
            print(f"    {i}. [{score:.3f}] {meta['source']} p.{meta['page']} "
                  f"({meta['drone_model']})")

        answer = generate_answer(question, chunks)
        print(f"\nA: {answer}\n")


if __name__ == "__main__":
    main()
