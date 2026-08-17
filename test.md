# RAG Pipeline Optimization — Experiment Log

## System Overview

RAG pipeline for 3 DJI drone manuals (Air 3, Mini 4 Pro, Mavic 3 Classic). Evaluated using RAGAS metrics with GPT-4o-mini as judge on a golden dataset of 12 questions.

**Metrics tracked:**
- **Faithfulness** — Is the answer grounded in retrieved context? (no hallucination)
- **Answer Relevancy** — Does the answer address the question asked?
- **Context Precision** — Are retrieved chunks actually relevant to the question?
- **Context Recall** — Does retrieved context cover everything needed to answer?

---

## Experiment 1: Baseline Discovery (The top_k Bug)

**Config:** Fixed-length chunks 1500/300, top_k=50 in eval, retrieval_k=20, ms-marco-MiniLM-L-6-v2 reranker

**Results:**
| Faith | Relevancy | Precision | Recall |
|-------|-----------|-----------|--------|
| 0.87  | 0.87      | 0.63      | 0.90   |

**Problem:** Precision stuck at 0.63 no matter what parameters I tuned. Tried retrieval_k=40, top_k=4 in retriever — nothing helped.

**Root cause discovered:** The evaluation script was passing `top_k=50` to the retrieve function, but `retrieval_k=20` only fetches 20 chunks from Qdrant. The reranker was told "keep best 50" but only had 20 — so it returned ALL of them unfiltered. I was evaluating a system with no reranking at all.

**Fix:** Set eval `top_k=5` to match production behavior.

---

## Experiment 2: Proper top_k Evaluation

**Config:** Same chunking, top_k=5 in eval, retrieval_k=20, MiniLM-L-6 reranker

**Results:**
| Faith | Relevancy | Precision | Recall |
|-------|-----------|-----------|--------|
| 0.89  | 0.81      | 0.79      | 0.83   |

**Improvement:** Precision jumped 0.63 → 0.79 just by measuring correctly. The reranker was working all along.

**Thinking:** Now that I'm measuring the real system, which parameter moves precision further?

---

## Experiment 3: top_k=4 (Tighter Filtering)

**Config:** top_k=4, retrieval_k=20, MiniLM-L-6 reranker

**Results:**
| Faith | Relevancy | Precision | Recall |
|-------|-----------|-----------|--------|
| 0.925 | 0.865     | 0.814     | 0.855  |

**Why it helped:** Dropping from 5 → 4 chunks removed the weakest result that was often "related but not answering." Faithfulness spiked because less noise = less hallucination.

**This became the baseline to beat.**

---

## Experiment 4: Temperature 0.1 (Generation Tuning)

**Config:** top_k=4, temp=0.1, MiniLM-L-6 reranker

**Results:**
| Faith | Relevancy | Precision | Recall |
|-------|-----------|-----------|--------|
| 0.913 | 0.86      | 0.779     | 0.83   |

**Why it failed:** Slightly worse across the board. Temperature 0.2 was already low enough for factual Q&A. The variance was likely just RAGAS judge noise — with only 12 questions, ±2-3% between identical runs is normal.

**Reverted to temp=0.2.**

---

## Experiment 5: Semantic Chunking (Heuristic Headers)

**Config:** Document-aware chunking from ingest_documentaware.py, section-based splitting using header detection heuristics

**Results:**
| Faith | Relevancy | Precision | Recall |
|-------|-----------|-----------|--------|
| 0.86  | 0.71      | 0.72      | 0.73   |

**Why it failed badly:**
1. **No overlap between chunks** — if a relevant passage straddled a section boundary, it was lost entirely
2. **Aggressive header detection** — misclassified content lines as headers, fragmenting coherent passages
3. **Small section merging** — merged unrelated tiny sections into incoherent chunks that matched both topics weakly

**Lesson:** Heuristic section detection isn't "semantic" chunking. It's brittle regex-based splitting that fragments more than it helps for technical manuals.

---

## Experiment 6: True Semantic Chunking (Embedding-Based Boundaries)

**Config:** Split into sentences, embed sentence groups, detect topic boundaries by cosine similarity drops (threshold 0.78)

**Results:**
| Faith | Relevancy | Precision | Recall |
|-------|-----------|-----------|--------|
| 0.84  | 0.56      | 0.67      | 0.51   |

**Why it failed catastrophically:**
- DJI manuals aren't clean prose — they're spec tables, bullet lists, numbered steps, short lines
- The sentence splitter mangled structured content (spec lines don't end with periods)
- Adjacent topics in technical docs share vocabulary, so embedding similarity stays high across real topic boundaries
- Chunks ended up either too fragmented or merged incoherently

**Lesson:** Semantic chunking works for long-form prose (articles, papers). For mixed-format technical manuals, fixed-length with overlap is more robust. The overlap acts as insurance against lost information.

**Reverted to fixed-length 1500/300.**

---

## Experiment 7: Upgraded Reranker (BAAI/bge-reranker-base)

**Config:** Fixed 1500/300, top_k=4, bge-reranker-base (278M params) replacing ms-marco-MiniLM-L-6-v2 (22M params)

**Results:**
| Faith | Relevancy | Precision | Recall |
|-------|-----------|-----------|--------|
| 0.922 | 0.857     | **0.924** | 0.875  |

**Why it worked:** The larger reranker (12 layers vs 6) has much deeper language understanding. It distinguishes "this chunk mentions the topic" from "this chunk actually answers the question." The MiniLM was making ranking errors — putting related-but-not-answering chunks above truly relevant ones.

**Precision: 0.81 → 0.92.** Single biggest lever in the entire optimization.

---

## Experiment 8: Hybrid Search (BM25 + Dense)

**Config:** Fixed 1500/300, top_k=4, bge-reranker, BM25 keyword search + dense semantic search merged before reranking

**Results:**
| Faith | Relevancy | Precision | Recall |
|-------|-----------|-----------|--------|
| 0.854 | 0.867     | **0.940** | **0.908** |

**Why it helped retrieval:** BM25 catches exact keyword matches that embeddings miss. Query "What is the RC-N2?" — embeddings match "remote controller" generally, BM25 pinpoints chunks containing literal "RC-N2."

**Why faithfulness dipped (0.92 → 0.85):** BM25 sometimes surfaces chunks with the right keywords but wrong context. The LLM then uses loosely-relevant info to make claims not fully supported.

**Trade-off:** Best retrieval metrics ever, but generation quality dropped.

---

## Experiment 9: Parent-Child Chunking + Hybrid Search (WINNER)

**Config:** Parent chunks 1500 chars, child chunks 300 chars. Search on children (precise embeddings), expand to parents for LLM context. Hybrid BM25+dense on children, rerank against parent text, top_k=4, bge-reranker-base.

**Results:**
| Faith | Relevancy | Precision | Recall |
|-------|-----------|-----------|--------|
| **0.958** | **0.922** | **0.936** | **0.933** |

**Why everything improved:**
- **Small children (300 chars)** embed very precisely — a chunk about "max speed 21 m/s" matches perfectly against "how fast is the Air 3?"
- **Large parents (1500 chars)** give the LLM full surrounding context — no hallucination from fragments
- **Parent deduplication** prevents wasting top_k slots on multiple children from the same paragraph
- **Reranking against parent text** ensures the reranker judges what the LLM will actually see
- **Fixed the hybrid faithfulness problem** — even if BM25 surfaces a noisy child, the parent provides full context that prevents hallucination

---

## Summary: What Mattered Most

| Change | Primary Impact | Magnitude |
|--------|---------------|-----------|
| Fix eval top_k bug | Precision | +0.16 |
| Upgrade reranker (MiniLM → BGE) | Precision | +0.11 |
| Parent-child chunking | All metrics | +0.02-0.10 |
| Hybrid search (BM25 + dense) | Recall | +0.03 |
| top_k 5→4 | Faithfulness | +0.03 |
| Semantic chunking | All metrics | -0.10 to -0.30 (NEGATIVE) |
| Temperature tuning | Negligible | ±0.01 |

## Final Production Config

- **Chunking:** Parent-child (1500/300 chars)
- **Search:** Hybrid (BM25 + dense embedding)
- **Embedding:** text-embedding-3-small (1536 dims)
- **Reranker:** BAAI/bge-reranker-base
- **top_k:** 4 (retrieval_k=30 for parent-child)
- **LLM:** gpt-4o-mini, temperature 0.2
- **Vector store:** Qdrant, collection dji_manuals_parent_child
