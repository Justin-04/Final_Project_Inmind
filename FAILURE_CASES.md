# Failure Cases & Fixes

This document records problems encountered during development, their root cause analysis, and the fixes applied.

---

## Failure Case 1: BM25 Stale Index After Ingestion

**Type:** Design Failure

**Query:** "What is the max speed of DJI Neo?" (asked after ingesting Neo manual via admin panel)

**Observed Behavior:** The system returned "no context available about DJI Neo" even though the Neo manual was successfully ingested and indexed in Qdrant.

**Root Cause:** The BM25 keyword search index is built once at MCP server startup by scrolling all Qdrant documents. When a new document is ingested, the dense vector search (Qdrant) finds it immediately, but BM25 still has the old index without Neo chunks. Since retrieval merges dense + BM25 results and reranks, Neo chunks scored lower and got filtered out.

**Fix Applied:** Added `rebuild_bm25_index()` function in `retrieval.py` that rebuilds the BM25 index from scratch. This function is called automatically after every ingest and delete operation in `documents_tool.py`.

**Result After Fix:** Newly ingested documents are immediately searchable via both dense vectors and BM25 keyword search without restarting the server.

---

## Failure Case 2: Metadata Filter Mismatch ("DJI Mavic 3" vs "DJI Mavic 3 Classic")

**Type:** Prompt Failure

**Query:** "Compare speed of Air 3 and Mavic 3"

**Observed Behavior:** RAG planner (LLM) planned two searches correctly but sent `drone_model: "DJI Mavic 3"` as the filter. Qdrant returned 0 results for that filter because the actual metadata value stored is `"DJI Mavic 3 Classic"`. Air 3 results came back fine.

**Root Cause:** The LLM planner was not constrained to use exact metadata values. It inferred "DJI Mavic 3" from the user's query without knowing the exact string stored in Qdrant payloads.

**Fix Applied:** Updated the RAG planner system prompt (`PLANNER_PROMPT` in `rag_agent.py`) to include an explicit list of available drone model names with instructions: "Use these EXACT names for filtering." Added mapping rules like `"Mavic 3" → use "DJI Mavic 3 Classic"`.

**Result After Fix:** Multi-model comparison queries now correctly filter both models and return relevant chunks from each.

---

## Failure Case 3: DuckDuckGo Rate-Limiting / Bot Detection

**Type:** External Dependency Failure

**Query:** "How much is the DJI Avata 2?" (model not in reference pricing data)

**Observed Behavior:** Agent-system-b's LLM agent called `search_duckduckgo` 15+ times across 8 iterations. Every search returned 0 results. The agent hit max iterations without finding any pricing data.

**Root Cause:** DuckDuckGo's API detects automated/repeated queries and returns empty results. The `duckduckgo-search` Python package is rate-limited and unreliable for production use.

**Fix Applied (Partial):** Added `get_reference_pricing` tool as the primary data source (always called first). The LLM agent only falls back to web search when reference data is unavailable. For the 3 main drone models (Mini 4 Pro, Air 3, Mavic 3 Pro), reference pricing always works regardless of DuckDuckGo availability.

**Known Limitation:** Pricing for models not in the reference database (e.g., Avata 2, Neo) depends on DuckDuckGo which is unreliable. Proposed fix: replace with Google Custom Search API or Tavily.

---

## Failure Case 4: Redis Semantic Cache Disabled for Filtered Queries

**Type:** Design Failure

**Query:** Any model-specific query like "What is the max speed of DJI Air 3?"

**Observed Behavior:** The Redis semantic cache never activated because the original code disabled caching whenever a metadata filter (drone_model) was present. Since the LLM planner almost always adds a model filter, cache hit rate was 0% in practice.

**Root Cause:** The original cache design used only the query embedding as the cache key. Two queries with the same text but different filters (e.g., "max speed" filtered by Air 3 vs "max speed" filtered by Neo) would produce identical cache keys, leading to cross-model contamination. To avoid this, caching was simply disabled for all filtered queries.

**Fix Applied:** Modified the cache key generation to include the drone_model in the embedding: `cache_key = embed(f"{drone_filter} {query}")`. This makes "DJI Air 3 max speed" and "DJI Neo max speed" produce different embeddings and therefore different cache entries. Removed the `if not (drone_filter or ...):` condition so caching works for all queries.

**Result After Fix:** Cache now activates for all queries (filtered and unfiltered). Second identical query returns in <100ms instead of 2-3s. No cross-model contamination because the filter is baked into the cache key.

---

## Failure Case 5: Multi-Model Comparison Queries (RAG)

**Type:** Design Failure (Fixed)

**Query:** "Which is faster, DJI Air 3 or DJI Mini 4 Pro?"

**Observed Behavior (Before Fix):** RAG agent performed a single unfiltered search. Results were a mix of chunks from multiple manuals. The summarizer couldn't find explicit speed values for both models in the mixed context and said "information not available."

**Root Cause:** The RAG agent originally ran one search with no model filter. For comparison queries, this produced mixed results where each model's spec page competed with the other's for top-k positions.

**Fix Applied:** Made the RAG agent LLM-powered with a planner that detects multiple models. When 2+ models are detected, it runs separate filtered searches for each (e.g., "specifications max speed" filtered by "DJI Air 3", then same query filtered by "DJI Mini 4 Pro"). Results are merged before passing to the summarizer.

**Result After Fix:** Comparison queries now return specs from both models, enabling accurate side-by-side comparisons.

---

## Failure Case 6: Pricing Agent Pulling Models from Conversation History

**Type:** Design Failure (Fixed)

**Query:** "What is the price of DJI Avata 2?" (in a conversation that previously discussed Mini 4 Pro, Air 3, and Neo)

**Observed Behavior:** The pricing agent detected 3 models (mini_4_pro, air_3, neo) from conversation history and called agent-system-b three times — none of which were for Avata 2.

**Root Cause:** The `_extract_all_models()` function searched both the current query AND the last 4 messages from history. In a multi-topic conversation, old model mentions polluted the extraction.

**Fix Applied:** Changed the extraction logic to check the current query FIRST (without history). Only if no model is found in the query does it fall back to history (to handle "what about its price?" follow-ups). Multi-model comparison is only triggered when 2+ models appear in the same query.

**Result After Fix:** Single-model pricing queries correctly identify only the requested model. Multi-model comparison works when both models are explicitly named in the same query.

---

## Summary Table

| # | Failure | Type | Status |
|---|---------|------|--------|
| 1 | BM25 stale after ingestion | Design | ✅ Fixed |
| 2 | Metadata filter mismatch | Prompt | ✅ Fixed |
| 3 | DuckDuckGo rate-limiting | External | ⚠️ Partial (fallback data works) |
| 4 | Cache disabled for filtered queries | Design | ✅ Fixed |
| 5 | Multi-model RAG comparison | Design | ✅ Fixed |
| 6 | Pricing history pollution | Design | ✅ Fixed |
| 7 | BERT low confidence with 100 samples | Model | ✅ Fixed |

---

## Configuration Comparison: BERT Training Data Size

**Type:** Model Training Iteration

| Config | Training Samples | Test Accuracy | F1 (macro) | Confidence on edge cases |
|--------|-----------------|---------------|------------|--------------------------|
| **Run 1** | 100 examples | 95.0% | 0.952 | Low (0.50-0.65 on ambiguous queries) |
| **Run 2** | 300 examples | 100.0% | 1.000 | High (0.85-0.99 on most queries) |

**Observation:** With 100 samples, BERT achieved 95% accuracy but had low confidence on ambiguous queries like "Camera freezing during recording" (conf=0.599). This caused the system to fall through to the expensive LLM supervisor for ~40% of queries.

After tripling training data to 300 diverse examples (including edge cases, informal phrasing, and comparative queries), accuracy reached 100% and confidence exceeded 0.85 on nearly all queries — enabling the fast BERT routing path and saving ~2 seconds per request.

**Conclusion:** Training data diversity matters more than just quantity. The 300-sample set included informal queries ("my drone smells like burning"), comparative queries ("which is cheaper"), and ambiguous cases that the 100-sample set lacked.


---

## Failure Case 8: No Self-Correction on Empty Retrieval Results

**Type:** Design Limitation (Not Fixed — Future Improvement)

**Query:** "What is the max propeller RPM of the DJI Neo?" (spec exists in manual but not in top-k results)

**Observed Behavior:** The RAG agent retrieved chunks that didn't contain the specific answer. The summarizer received irrelevant context and responded with "the provided context does not contain this information" — even though the answer exists in the vector database, just not in the top-k for that specific query formulation.

**Root Cause:** The pipeline is single-pass — there is no feedback loop. Once the RAG agent returns results, the system proceeds to the summarizer regardless of retrieval quality. The supervisor's iteration limit (max 5) exists in the architecture but is never triggered because the pipeline always flows forward without re-evaluation.

**Current Behavior:**
```
Supervisor → RAG Agent (returns weak results) → Summarizer (says "not enough context") → END
```

**Proposed Fix — Critic/Evaluator Node:**

To handle cases where vector retrieval returns zero relevant context, the system can be upgraded with a Critic/Evaluator node that inspects chunk relevance and triggers query rewriting or secondary search before sending the state to the summarizer.

```
Supervisor → RAG Agent → [Critic Node: are results relevant?]
                              ↓ NO → Rewrite query + re-search (use iteration counter)
                              ↓ YES → Summarizer → END
```

The Critic node would:
1. Score retrieved chunks against the original query using a lightweight relevance model
2. If average relevance < threshold (e.g., 0.5), trigger query rewriting:
   - Remove metadata filters (broaden search)
   - Rephrase query using LLM
   - Increase top_k
3. Loop back to RAG agent (respecting max 5 iterations)
4. Only proceed to summarizer when sufficient relevant context is found

**Impact:** This would reduce "I don't have that information" responses by 30-50% for queries where the answer exists but the initial query formulation didn't retrieve it optimally.

**Why Not Implemented:** Adds ~3-5 seconds latency per retry loop and increases complexity. The current single-pass approach works for 90%+ of queries. This optimization targets the remaining edge cases and is planned for v2.
