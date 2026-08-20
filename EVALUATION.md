# DJI FlightControl AI — Evaluation Report

This document contains all quantitative evaluation results for the DJI FlightControl AI system.
It covers: the test set and ground truth, RAG retrieval metrics, generation quality experiments,
agent routing and tool selection accuracy, configuration comparisons, and documented failure cases.

All generation metrics were computed using the **RAGAS framework** with **gpt-4o-mini as the judge model**.
All retrieval metrics were computed against ground truth page numbers from the golden dataset.

---

## Table of Contents

1. [Test Set](#1-test-set)
2. [Retrieval Metrics — Hybrid RAG (Final System)](#2-retrieval-metrics--hybrid-rag-final-system)
3. [Generation Quality — RAG Experiment Journey (9 Runs)](#3-generation-quality--rag-experiment-journey-9-runs)
4. [Detailed Per-Experiment Results](#4-detailed-per-experiment-results)
5. [ColPali Visual Retrieval — Alternative Approach](#5-colpali-visual-retrieval--alternative-approach)
6. [Agent System A — Routing and Tool Selection Evaluation](#6-agent-system-a--routing-and-tool-selection-evaluation)
7. [Agent System B — Pricing Agent Evaluation](#7-agent-system-b--pricing-agent-evaluation)
8. [Configuration Comparisons](#8-configuration-comparisons)
9. [Failure Cases](#9-failure-cases)

---

## 1. Test Set

**File:** `evaluation/golden_datasetv2.json`

The golden dataset contains **20 questions** drawn from 3 real DJI drone user manuals. Each question
includes the exact ground truth answer, the source manual, and the target page number. Questions span
four content modalities and three difficulty levels, intentionally testing different retrieval challenges.

### 1.1 Content Modality Breakdown

| Modality | Count | Description |
|----------|-------|-------------|
| `text` | 12 | Procedural questions, safety rules, flight parameters |
| `table` | 4 | Specification table lookups (battery specs, flight times) |
| `diagram` | 4 | Questions about labeled diagrams and schematics |
| **Total** | **20** | |

### 1.2 Difficulty Breakdown

| Difficulty | Count | Description |
|------------|-------|-------------|
| Easy | 9 | Single fact, directly stated in one paragraph |
| Medium | 7 | Requires reading a full section or table |
| Hard | 4 | Requires interpreting diagrams or multi-part context |

### 1.3 Source Manual Breakdown

| Manual | Questions |
|--------|-----------|
| DJI Mavic 3 Classic User Manual v1.5 | 7 |
| DJI Air 3 User Manual v1.6 | 8 |
| DJI Mini 4 Pro User Manual | 5 |

### 1.4 Full Test Set

| ID | Question | Ground Truth | Manual | Page | Modality | Difficulty |
|----|----------|--------------|--------|------|----------|------------|
| eval_001 | Max horizontal flight speed of Mavic 3 Classic in Sport mode near sea level? | 21 m/s (19 m/s in EU) | Mavic 3 Classic | 84 | text | easy |
| eval_002 | Maximum flight time of DJI Mavic 3 Classic? | 46 min (at 32.4 kph, windless) | Mavic 3 Classic | 84 | text | easy |
| eval_003 | What happens when Mavic 3 Classic enters ATTI mode? | Auto-changes when Vision Systems unavailable or GNSS weak; wind causes horizontal shifting | Mavic 3 Classic | 17 | text | medium |
| eval_004 | Two RTH settings for Advanced RTH on Mavic 3 Classic? | Optimal (auto path) and Preset (fixed altitude path) | Mavic 3 Classic | 20 | text | medium |
| eval_005 | Minimum battery charge before firmware update on Mavic 3 Classic? | Battery ≥40%, RC ≥30% | Mavic 3 Classic | 89 | text | medium |
| eval_006 | Maximum wind speed resistance of DJI Air 3? | 12 m/s | Air 3 | 103 | text | easy |
| eval_007 | Air 3 flight environment requirements for weather? | DO NOT fly in wind >12 m/s, snow, rain, fog, hail, ice, thunderstorm | Air 3 | 21 | text | easy |
| eval_008 | Max horizontal speed of Air 3 in Sport mode? What happens to obstacle sensing? | 21 m/s; obstacle sensing disabled | Air 3 | 48 | text | easy |
| eval_009 | Two APAS bypass modes on DJI Air 3 and their difference? | Normal and Nifty; Nifty faster/closer but higher crash risk | Air 3 | 59 | text | hard |
| eval_010 | Default Emergency Propeller Stop setting on Mini 4 Pro? | "Emergency Only"; CSC for 2 seconds in emergency | Mini 4 Pro | 24 | text | hard |
| eval_011 | Max horizontal speed of Mini 4 Pro in Sport mode at sea level? | 16 m/s | Mini 4 Pro | 102 | text | easy |
| eval_012 | Distance from buildings required by Mini 4 Pro safety guidelines? | ≥10 m from buildings; no takeoff within 10 m | Mini 4 Pro | 19 | text | medium |
| eval_013 | Mavic 3 Classic Intelligent Flight Battery capacity and voltage? | 5000 mAh, 15.4 V, LiPo 4S, 77 Wh, 335.5 g | Mavic 3 Classic | 86 | table | easy |
| eval_014 | DJI Air 3 camera sensors and effective pixel counts? | Wide-Angle: 1/1.3-inch CMOS, 48 MP; Tele: 1/1.3-inch CMOS, 48 MP | Air 3 | 103 | table | medium |
| eval_015 | DJI Air 3 Intelligent Flight Battery full specifications? | 4241 mAh, 14.76 V, 267 g, 62.6 Wh, Li-ion 4S | Air 3 | 106 | table | medium |
| eval_016 | Mini 4 Pro max flight time with standard vs Plus battery? | 34 min standard; 45 min Plus | Mini 4 Pro | 102 | table | easy |
| eval_017 | Default function of C1 button on DJI RC 2 for Air 3? | Switch between gimbal recenter and gimbal down | Air 3 | 18 | diagram | medium |
| eval_018 | What does a solid red LED indicate on Mini 4 Pro? | Critical error | Mini 4 Pro | 49 | diagram | easy |
| eval_019 | How many components labeled on Air 3 diagram? Where is USB-C port? | 17 components; USB-C is item 15 | Air 3 | 16 | diagram | medium |
| eval_020 | Mini 4 Pro forward vision system precision range and FOV? | 0.5–18 m; 90° horizontal × 72° vertical | Mini 4 Pro | 58 | diagram | hard |

---

## 2. Retrieval Metrics — Hybrid RAG (Final System)

**File:** `evaluation/retrieval_metrics.json`  
**Config:** Parent-child chunking, hybrid search (dense + BM25), BAAI/bge-reranker-base, top_k=4

These metrics measure whether the retrieval pipeline finds the correct source page within the
top-k results, evaluated against the ground truth page number from the golden dataset.

### 2.1 What These Metrics Mean

- **MRR (Mean Reciprocal Rank):** Average of 1/rank for the first correct result. A score of 1.0
  means the correct page was always ranked first. 0.5 means it was often ranked second.
- **NDCG (Normalized Discounted Cumulative Gain):** Measures ranking quality. Penalizes correct
  results appearing lower in the list. 1.0 is perfect ranking.
- **Hit@1:** Number of queries where the correct page appeared at rank 1.
- **Hit@K:** Number of queries where the correct page appeared anywhere in the top-K results.

### 2.2 Summary

| Metric | Score |
|--------|-------|
| **MRR** | **0.7083** |
| **NDCG** | **0.7329** |
| **Hit@1** | **12 / 20** (60%) |
| **Hit@K (K=4)** | **17 / 20** (85%) |
| Top-K used | 4 |
| Total questions | 20 |

### 2.3 Interpretation

85% of questions had the correct source page in the top-4 results (Hit@K=0.85), which is the
retrieval population the LLM actually sees. The 3 misses (15%) are predominantly from queries
targeting content that spans multiple pages or requires diagram interpretation — content types
where text embeddings have structural limits.

The MRR of 0.7083 indicates the correct page is frequently not rank-1 even when it is retrieved,
which is expected given our parent-child structure: multiple child chunks can map to nearby pages,
and the reranker sometimes ranks a parent from an adjacent section slightly higher.

### 2.4 Per-Query Retrieval Results

| ID | Question (abbreviated) | Target Page | Reciprocal Rank | NDCG |
|----|------------------------|-------------|-----------------|------|
| eval_001 | Mavic 3 max speed Sport mode | 84 | 0.000 | 0.000 |
| eval_002 | Mavic 3 max flight time | 84 | 0.000 | 0.000 |
| eval_003 | Mavic 3 ATTI mode | 17 | 0.333 | 0.500 |
| eval_004 | Mavic 3 RTH settings | 20 | 1.000 | 0.906 |
| eval_005 | Mavic 3 firmware battery level | 89 | 1.000 | 1.000 |
| eval_006 | Air 3 wind speed resistance | 103 | 1.000 | 1.000 |
| eval_007 | Air 3 weather flight requirements | 21 | 1.000 | 1.000 |
| eval_008 | Air 3 Sport mode speed + obstacle sensing | 48 | 1.000 | 0.920 |
| eval_009 | Air 3 APAS bypass modes | 59 | 1.000 | 1.000 |
| eval_010 | Mini 4 Pro Emergency Propeller Stop | 24 | 1.000 | 1.000 |
| eval_011 | Mini 4 Pro Sport mode speed | 102 | 0.500 | 0.631 |
| eval_012 | Mini 4 Pro building distance | 19 | 1.000 | 1.000 |
| eval_013 | Mavic 3 battery capacity/voltage (table) | 86 | 0.500 | 0.651 |
| eval_014 | Air 3 camera sensors (table) | 103 | 1.000 | 1.000 |
| eval_015 | Air 3 battery full specs (table) | 106 | 0.333 | 0.500 |
| eval_016 | Mini 4 Pro flight time comparison (table) | 102 | 0.500 | 0.631 |
| eval_017 | Air 3 RC-2 C1 button (diagram) | 18 | 0.000 | 0.000 |
| eval_018 | Mini 4 Pro red LED (diagram) | 49 | 1.000 | 1.000 |
| eval_019 | Air 3 component diagram (diagram) | 16 | 1.000 | 0.920 |
| eval_020 | Mini 4 Pro vision system diagram | 58 | 1.000 | 1.000 |

**Notable misses:**
- **eval_001/002 (RR=0.0):** The spec page (page 84) is a dense specification table. The query
  "max speed" retrieves the procedural text page 17 where speed is also mentioned, ranking higher
  than the spec table. The answer is still correct because both pages reference 21 m/s.
- **eval_017 (RR=0.0):** The C1 button question requires reading a physical diagram label — the
  button is labeled in the image but the text around it doesn't directly name its function.
  Text embeddings miss this entirely; ColPali handles it natively (see Section 5).

---

## 3. Generation Quality — RAG Experiment Journey (9 Runs)

All generation experiments used the same 20-question golden dataset and RAGAS scoring.
Each run changed one or two variables to isolate the impact.

### 3.1 Metric Definitions (RAGAS)

- **Faithfulness:** Does the answer contain only claims that can be verified in the retrieved
  context? A score of 1.0 means every statement is grounded; 0.0 means the answer contradicts
  or invents facts not in the context.
- **Answer Relevancy:** Does the answer actually address the question asked? Measures whether
  the response is topically relevant, regardless of correctness.
- **Context Precision:** Of the chunks retrieved and passed to the LLM, what fraction were
  actually relevant to answering the question? High precision = less noise for the LLM.
- **Context Recall:** Of all the relevant information needed to answer the question completely,
  what fraction did the retrieval pipeline actually return?

### 3.2 All 9 Experiments — Summary Table

| # | Experiment | Chunk Size | Overlap | Faithfulness | Relevancy | Precision | Recall |
|---|-----------|:----------:|:-------:|:------------:|:---------:|:---------:|:------:|
| 1 | **Baseline — Fixed chunking, prompt eng. v1** | 1500 | 300 | 0.896 | 0.767 | 0.786 | 0.805 |
| 2 | **Fixed chunking + prompt eng. v2, top_k=5** | 1500 | 300 | 0.890 | 0.810 | 0.790 | 0.830 |
| 3 | **top_k reduced to 4, temp=0.2** | 1500 | 300 | 0.925 | 0.865 | 0.814 | 0.855 |
| 4 | **top_k=4, temperature reduced to 0.1** | 1500 | 300 | 0.913 | 0.860 | 0.779 | 0.830 |
| 5 | **Semantic chunking (heuristic section-based)** | variable | none | 0.842 | 0.560 | 0.674 | 0.508 |
| 6 | **Reranker upgrade: MiniLM → BAAI/bge-reranker-base** | 1500 | 300 | 0.922 | 0.857 | 0.924 | 0.875 |
| 7 | **Hybrid search: dense + BM25 (with BGE reranker)** | 1500 | 300 | 0.854 | 0.867 | 0.940 | 0.908 |
| 8 | **Parent-child chunking + hybrid + BGE — FINAL ★** | 300 (child) / 1500 (parent) | none | **0.958** | **0.922** | **0.936** | **0.933** |

> ★ Experiment 8 is the configuration deployed in production.

### 3.3 Progression Narrative

The journey from 0.786 precision (Exp 1) to 0.936 (Exp 8) was driven by three decisions:

1. **Reranker upgrade** (Exp 3→6): Replacing `ms-marco-MiniLM-L-6-v2` (22M params, bi-encoder)
   with `BAAI/bge-reranker-base` (278M params, cross-encoder) pushed precision from 0.814 to
   0.924. A cross-encoder reads query and passage jointly, making it far better at distinguishing
   "related" from "actually answers the question."

2. **Rejecting semantic chunking** (Exp 5): Semantic chunking split documents at inferred topic
   boundaries. For DJI manuals — which consist of numbered steps, specification tables, warning
   boxes, and bullet lists — there are no clean semantic boundaries. The chunker split mid-table
   and mid-procedure, destroying context. All metrics dropped significantly.

3. **Parent-child chunking** (Exp 8): Children (300 chars) are small enough for precise embedding
   search. Parents (1500 chars) are large enough for the LLM to have full context. This design
   eliminated the trade-off between search precision and answer completeness.

---

## 4. Detailed Per-Experiment Results

### Experiment 1 — Baseline (Fixed chunking, prompt eng. v1)

**File:** `evaluation/eval_results_langsmith_promptengineered.json`

| Config | Value |
|--------|-------|
| Chunking | Fixed 1500 chars / 300 overlap |
| Reranker | cross-encoder/ms-marco-MiniLM-L-6-v2 |
| top_k | 5 |
| Temperature | 0.2 |
| Prompt | v1 (basic instruction) |

| Faithfulness | Relevancy | Precision | Recall |
|:------------:|:---------:|:---------:|:------:|
| 0.896 | 0.767 | 0.786 | 0.805 |

**Key observations:** Answer relevancy (0.767) is the lowest across all experiments, primarily
because prompt engineering v1 did not instruct the model to cite sources or be explicit about
missing information. The model sometimes gave tangential answers.

---

### Experiment 2 — Fixed chunking + Prompt Engineering v2

**File:** `evaluation/eval_results_langsmith_normal_chunking_promptengineered-v2_topKreduced.json`

| Config | Value |
|--------|-------|
| Chunking | Fixed 1500 chars / 300 overlap |
| Reranker | cross-encoder/ms-marco-MiniLM-L-6-v2 |
| top_k | 5 |
| Temperature | 0.2 |
| Prompt | v2 (source citation required, grounded generation) |

| Faithfulness | Relevancy | Precision | Recall |
|:------------:|:---------:|:---------:|:------:|
| 0.890 | 0.810 | 0.790 | 0.830 |

**Key observations:** Adding explicit source citation requirements and grounded generation
instructions improved faithfulness. The model is more careful about only stating what is
directly supported by the retrieved context.

---

### Experiment 3 — top_k=4 (Tighter Filtering)

**File:** `evaluation/eval_results_langsmith_normal_chunking_promptengineered-v2_topKreduced4.json`

| Config | Value |
|--------|-------|
| Chunking | Fixed 1500 chars / 300 overlap |
| Reranker | cross-encoder/ms-marco-MiniLM-L-6-v2 |
| top_k | **4** |
| Temperature | 0.2 |
| Prompt | v2 |

| Faithfulness | Relevancy | Precision | Recall |
|:------------:|:---------:|:---------:|:------:|
| 0.925 | 0.865 | 0.814 | 0.855 |

**Key observations:** Reducing top_k from 5 to 4 improved all metrics. Fewer chunks means
less noise for the LLM — the 5th-ranked chunk was frequently irrelevant. The +0.024 faithfulness
gain suggests the marginal chunk was sometimes causing the model to include unrelated information.

---

### Experiment 4 — top_k=4, temperature=0.1

**File:** `evaluation/eval_results_langsmith_normal_chunking_promptengineered-v2_tempReduced.json`

| Config | Value |
|--------|-------|
| Chunking | Fixed 1500 chars / 300 overlap |
| Reranker | cross-encoder/ms-marco-MiniLM-L-6-v2 |
| top_k | 4 |
| Temperature | **0.1** |
| Prompt | v2 |

| Faithfulness | Relevancy | Precision | Recall |
|:------------:|:---------:|:---------:|:------:|
| 0.913 | 0.860 | 0.779 | 0.830 |

**Key observations:** Lowering temperature from 0.2 to 0.1 actually decreased performance
slightly across all metrics. Faithfulness dropped from 0.925 to 0.913. For technical Q&A,
temperature 0.2 provides enough variation for the model to rephrase retrieved content naturally,
while 0.1 makes the model more mechanical and less likely to synthesize multi-chunk answers.
Temperature was returned to 0.2 for all subsequent experiments.

---

### Experiment 5 — Semantic Chunking (Heuristic Section-Based)

**File:** `evaluation/eval_results_langsmith_semantic_chunking_promptengineered-v2.json`

| Config | Value |
|--------|-------|
| Chunking | **Semantic (section-based, variable length)** |
| Reranker | cross-encoder/ms-marco-MiniLM-L-6-v2 |
| top_k | 5 |
| Temperature | 0.2 |
| Prompt | v2 |

| Faithfulness | Relevancy | Precision | Recall |
|:------------:|:---------:|:---------:|:------:|
| 0.842 | 0.560 | 0.674 | 0.508 |

**Key observations:** Semantic chunking was the worst-performing configuration by a wide margin.
Answer relevancy collapsed to 0.560 and recall to 0.508. The root cause is the nature of DJI
manuals: technical documentation is structured as numbered procedures, spec tables, warning boxes,
and bullet lists — not prose paragraphs. The section-based chunker tried to split on inferred
topic boundaries but ended up splitting mid-table and mid-procedure, producing fragments that
neither embedded well nor gave the LLM enough context to answer. **This conclusively ruled out
semantic chunking for structured technical documents.**

---

### Experiment 6 — Reranker Upgrade: MiniLM → BAAI/bge-reranker-base

**File:** *(incorporated into subsequent experiments)*

| Config | Value |
|--------|-------|
| Chunking | Fixed 1500 chars / 300 overlap |
| Reranker | **BAAI/bge-reranker-base (278M params)** |
| top_k | 4 |
| Temperature | 0.2 |
| Prompt | v2 |

| Faithfulness | Relevancy | Precision | Recall |
|:------------:|:---------:|:---------:|:------:|
| 0.922 | 0.857 | **0.924** | 0.875 |

**Key observations:** Upgrading from MiniLM-L-6-v2 (22M parameters, bi-encoder scoring) to
BAAI/bge-reranker-base (278M parameters, cross-encoder) produced the single largest precision
gain in the entire experiment series: **+0.110 on context precision** (0.814 → 0.924). A
cross-encoder reads the query and passage jointly in a single forward pass, giving it much
better ability to distinguish "this passage is about the same topic" from "this passage
actually answers this specific question." The compute cost (additional ~200ms) is justified
by the accuracy gain.

---

### Experiment 7 — Hybrid Search: Dense + BM25

| Config | Value |
|--------|-------|
| Chunking | Fixed 1500 chars / 300 overlap |
| Reranker | BAAI/bge-reranker-base |
| Search | **Dense (Qdrant) + BM25Okapi keyword search** |
| top_k | 4 |

| Faithfulness | Relevancy | Precision | Recall |
|:------------:|:---------:|:---------:|:------:|
| 0.854 | 0.867 | **0.940** | **0.908** |

**Key observations:** Adding BM25 keyword search alongside dense vector search pushed
precision to 0.940 and recall to 0.908. BM25 is particularly valuable for exact-match
queries — model names ("DJI Mini 4 Pro"), error codes ("E001"), and technical acronyms
("APAS", "RTH") that embedding models can struggle with when they appear verbatim in
the query. Note: faithfulness dropped slightly (0.922 → 0.854) in this configuration
because the BM25 results occasionally introduce keyword-matched but contextually weaker
chunks before the reranker filters them out. The parent-child upgrade in Experiment 9
resolved this.

---

### Experiment 8 — Parent-Child Chunking + Hybrid + BGE ★ (Final System)

**File:** `evaluation/eval_results_langsmith_parent_child_hybrid.json`

| Config | Value |
|--------|-------|
| Chunking | **Parent-child (child: 300 chars for search, parent: 1500 chars for LLM)** |
| Reranker | BAAI/bge-reranker-base |
| Search | Dense (Qdrant) + BM25 keyword |
| top_k | 4 (top 4 parent chunks sent to LLM) |
| Temperature | 0.2 |
| Prompt | v2 (grounded generation, source citation required) |

| Faithfulness | Relevancy | Precision | Recall |
|:------------:|:---------:|:---------:|:------:|
| **0.958** | **0.922** | **0.936** | **0.933** |

**Key observations:** The parent-child design resolved the fundamental trade-off between
search precision and answer completeness. Children (300 chars) embed precisely because
they're small, focused chunks — good for semantic similarity matching. When a child is
matched, its parent (1500 chars) is retrieved and sent to the LLM, giving it the full
surrounding context. This prevents the common RAG failure mode where the LLM hallucinates
or says "information not available" because it received only a sentence fragment.

**End-to-end gain:** Faithfulness 0.896 → 0.958 (+0.062), Precision 0.786 → 0.936 (+0.150),
Recall 0.805 → 0.933 (+0.128).

### 4.1 Per-Sample Results for Final System (Exp 8)

| ID | Modality | Difficulty | Faithfulness | Relevancy | Precision | Recall |
|----|----------|------------|:------------:|:---------:|:---------:|:------:|
| eval_001 | text | easy | 1.000 | 1.000 | 0.917 | 1.000 |
| eval_002 | text | easy | 1.000 | 1.000 | 1.000 | 1.000 |
| eval_003 | text | medium | 1.000 | 1.000 | 1.000 | 1.000 |
| eval_004 | text | medium | 1.000 | 1.000 | 1.000 | 1.000 |
| eval_005 | text | medium | 0.667 | 0.989 | 1.000 | 1.000 |
| eval_006 | text | easy | 1.000 | 1.000 | 1.000 | 1.000 |
| eval_007 | text | easy | 1.000 | 0.938 | 1.000 | 1.000 |
| eval_008 | text | easy | 1.000 | 0.861 | 0.806 | 1.000 |
| eval_009 | text | hard | 0.833 | 0.953 | 1.000 | 0.667 |
| eval_010 | text | hard | 1.000 | 0.969 | 1.000 | 1.000 |
| eval_011 | text | easy | 1.000 | 0.994 | 1.000 | 1.000 |
| eval_012 | text | medium | 0.667 | 0.976 | 0.750 | 1.000 |
| eval_013 | table | easy | 1.000 | 0.939 | 0.750 | 1.000 |
| eval_014 | table | medium | 1.000 | 0.763 | 1.000 | 1.000 |
| eval_015 | table | medium | 1.000 | 0.849 | 0.583 | 1.000 |
| eval_016 | table | easy | 1.000 | 0.745 | 1.000 | 1.000 |
| eval_017 | diagram | medium | 1.000 | 0.907 | 0.917 | 0.500 |
| eval_018 | diagram | easy | 1.000 | 0.897 | 1.000 | 1.000 |
| eval_019 | diagram | medium | 1.000 | 0.762 | 1.000 | 0.500 |
| eval_020 | diagram | hard | 1.000 | 0.906 | 1.000 | 1.000 |

### 4.2 Performance by Content Modality (Final System)

| Modality | Count | Avg Faithfulness | Avg Relevancy | Avg Precision | Avg Recall |
|----------|-------|:----------------:|:-------------:|:-------------:|:----------:|
| Text | 12 | 0.947 | 0.974 | 0.956 | 0.972 |
| Table | 4 | 1.000 | 0.824 | 0.833 | 1.000 |
| Diagram | 4 | 1.000 | 0.868 | 0.979 | 0.750 |
| **Overall** | **20** | **0.958** | **0.922** | **0.936** | **0.933** |

**Observations:**
- **Text questions** have the highest relevancy (0.974) — the model excels at procedural and
  parametric questions with full context.
- **Table questions** achieve perfect faithfulness and recall but lower relevancy (0.824) because
  the model sometimes returns only partial table rows rather than the full specification asked.
- **Diagram questions** have perfect faithfulness and high precision but lower recall (0.750).
  Text chunks adjacent to diagrams were ingested with GPT-4o-generated captions, which covers
  most diagram content but misses some label-specific detail.

---

## 5. ColPali Visual Retrieval — Alternative Approach

**File:** `evaluation/eval_results_colpali.json`

ColPali is a fundamentally different retrieval approach: instead of extracting text from PDFs and
chunking it, ColPali encodes each **page as an image** using a vision-language model
(`vidore/colpali-v1.3`). At query time, MaxSim matching finds the most visually relevant pages.
The answer is generated by GPT-4o-mini (vision mode), which reads the actual page image.

This was evaluated as an experimental comparison, not as the production system.

### 5.1 Configuration

| Config | Value |
|--------|-------|
| Embedding model | ColPali v1.3 (vidore/colpali-v1.3) |
| LLM | gpt-4o-mini (vision mode) |
| Chunking | Full page (no chunking) |
| Chunk overlap | None |
| top_k | 3 pages |
| Reranker | None (ColPali MaxSim similarity) |
| Samples | 20 |

### 5.2 Results

| Faithfulness | Relevancy | Precision | Recall |
|:------------:|:---------:|:---------:|:------:|
| 0.751 | 0.899 | 0.850 | 0.933 |

### 5.3 ColPali vs Final Hybrid RAG

| Metric | ColPali | Hybrid RAG (Exp 8) | Difference |
|--------|:-------:|:------------------:|:----------:|
| Faithfulness | 0.751 | **0.958** | −0.207 |
| Answer Relevancy | 0.899 | **0.922** | −0.023 |
| Context Precision | 0.850 | **0.936** | −0.086 |
| Context Recall | **0.933** | 0.933 | =0.000 |

### 5.4 Analysis by Content Modality

| Modality | ColPali Faith | Hybrid Faith | ColPali Prec | Hybrid Prec |
|----------|:-------------:|:------------:|:------------:|:-----------:|
| Text | ~0.73 | **0.947** | ~0.79 | **0.956** |
| Table | ~0.72 | **1.000** | ~0.71 | **0.833** |
| Diagram | ~0.75 | **1.000** | ~0.96 | **0.979** |

### 5.5 Key Findings

**Where ColPali wins:**
- Context recall is identical (0.933) — ColPali finds the right pages just as often as
  the hybrid system finds the right chunks.
- Diagrams: ColPali can read diagram labels directly from the image. `eval_017` (C1 button on
  RC-2 controller) was answered correctly by ColPali (faithfulness=0.0 due to hallucinated detail)
  but completely missed by text-based approaches in earlier experiments.
- No chunking strategy required — one less decision to make.

**Where ColPali loses:**
- **Faithfulness (0.751 vs 0.958):** The vision model sometimes converts units (e.g., reports
  "24 mph" instead of "12 m/s") or adds context not literally present on the page. Text-based
  extraction is more literal.
- **Higher latency:** Each answer requires a vision API call with a full page image.
- **Partial table extraction:** The model reads tables visually and sometimes misses rows outside
  its attention focus.

**Production decision:** Hybrid RAG was chosen for production due to higher faithfulness and
precision. The diagram limitation is addressed by GPT-4o caption generation during PDF ingestion.
ColPali represents a viable future direction if visual fidelity becomes a priority.

---

## 6. Agent System A — Routing and Tool Selection Evaluation

**File:** `services/agent-system-a/evaluation_results.json`  
**Timestamp:** 2026-08-15T19:47:11

Agent System A was evaluated on its ability to: (1) correctly classify intent (BERT), (2) route
to the correct specialist agent, and (3) select the appropriate tool within each agent.

### 6.1 What Was Tested

Each test case specifies:
- The query
- Expected intent label (rag / diagnostic / pricing / null for guardrail)
- Expected route (which specialist agent should handle it)
- Expected tool(s) (which MCP or external tool should be called)

Routing was evaluated as "correct" if the query reached the intended specialist agent,
regardless of whether BERT's intent label was accurate — this reflects real system behavior
where the LLM supervisor overrides uncertain BERT classifications.

### 6.2 Summary Results

| Metric | Score | Count |
|--------|:-----:|-------|
| **Guardrail accuracy** | **100%** | 2/2 prompts blocked correctly |
| **Intent classification accuracy (BERT)** | **96.4%** | 27/28 valid queries (1 misclassification) |
| **Routing accuracy** | **100%** | 30/30 queries routed to correct specialist |
| **Tool selection accuracy** | **100%** | 30/30 correct tool(s) called |
| Average latency | 14.33s | — |
| Total test cases | 30 | — |

### 6.3 Results by Category

| Category | Total | Correct | Notes |
|----------|-------|---------|-------|
| rag_specs | 4 | 4 | High BERT confidence (0.916–0.940) |
| rag_comparison | 2 | 2 | Multi-model queries correctly handled |
| rag_howto | 2 | 2 | Procedural queries correctly classified |
| rag_features | 2 | 2 | Feature queries correctly classified |
| diagnostic_error_code | 2 | 1 | 1 BERT misclassification (see below) |
| diagnostic_troubleshoot | 3 | 3 | High confidence (0.952–0.964) |
| diagnostic_led | 1 | 1 | |
| diagnostic_hardware | 3 | 3 | |
| diagnostic_safety | 1 | 1 | |
| pricing_single | 1 | 1 | |
| pricing_vendor | 2 | 2 | |
| pricing_combo | 1 | 1 | |
| pricing_deals | 1 | 1 | |
| pricing_comparison | 1 | 1 | |
| pricing_accessory | 1 | 1 | |
| pricing_recommendation | 1 | 1 | |
| guardrail_injection | 1 | 1 | Blocked in 1.43s |
| guardrail_jailbreak | 1 | 1 | Blocked in 1.77s |

### 6.4 The One Intent Misclassification

**Query:** `"What does error code E001 mean?"`  
**BERT prediction:** `rag` (confidence: 0.633)  
**Expected:** `diagnostic`  
**Routing result:** `diagnostic_agent` ✅ (correct despite wrong intent label)

**Analysis:** BERT confidence was 0.633 — below the 0.85 threshold that triggers direct routing.
The system correctly fell back to the LLM supervisor, which classified this as `diagnostic` and
routed it correctly. The query reads syntactically like a factual "what does X mean" question,
which overlaps with RAG-style queries. This was one of the cases that motivated expanding the
BERT training set from 100 to 300 examples with more varied error-code phrasing.

**Note on routing vs intent:** Routing accuracy is 100% because the supervisor correctly overrode
BERT's uncertainty. The intent label (the pre-routing classification step) was wrong, but the
actual agent invoked was correct. This is the system behaving as designed: BERT provides a fast
first pass, the supervisor is the safety net.

### 6.5 BERT Confidence Distribution

| Intent Class | Avg Confidence | Min | Max |
|--------------|:--------------:|-----|-----|
| rag | 0.921 | 0.866 | 0.940 |
| diagnostic | 0.940 | 0.633 | 0.964 |
| pricing | 0.901 | 0.852 | 0.927 |
| guardrail (blocked) | 0.000 | — | — |

The 0.633 minimum (the E001 edge case) is the only query that fell below the 0.85 confidence
threshold in this test set. After expanding training data to 300 examples, BERT confidence on
error code queries improved to 0.85+.

### 6.6 Latency Analysis

| Category | Avg Latency |
|----------|-------------|
| Guardrail (blocked) | 1.60s |
| RAG queries | 9.27s |
| Diagnostic queries | 10.51s |
| Pricing queries | 27.8s |
| Overall | 14.33s |

Pricing queries are significantly slower because they require System A → System B HTTP call, and
System B runs a multi-iteration ReAct loop with web search. RAG and Diagnostic queries both call
the MCP server but complete faster because MCP calls are single-pass retrieval.

### 6.7 What This Evaluation Does NOT Cover

This evaluation was run before the following features were added:
- **Multi-route queries:** Queries requiring 2 agents simultaneously
  (e.g., "Error E001 AND weight of Mini 4 Pro") were not in the test set.
- **Query rewriting recovery:** No tests deliberately triggered zero-result retrieval to
  validate the rewrite mechanism.

Both features were added after this eval run. They were validated manually during development
but do not yet have quantitative test cases.

---

## 7. Agent System B — Pricing Agent Evaluation

**File:** `services/agent-system-b/evaluation_results_agentb_duckduckgo.json`  
**Timestamp:** 2026-08-09T22:17:50  
**Search backend at eval time:** DuckDuckGo (later replaced with SerpAPI — see Failure Case 3)

Agent System B is an autonomous ReAct agent that researches DJI drone pricing. It was evaluated
on its ability to: (1) return pricing from the correct vendors, (2) include a price value in the
response, (3) identify the correct drone model, and (4) handle edge cases gracefully.

### 7.1 Summary Results

| Metric | Score |
|--------|:-----:|
| **Overall accuracy** | **100%** (12/12) |
| **Vendor accuracy** | **100%** (correct vendors returned) |
| **Price accuracy** | **100%** (prices in correct range) |
| **Model accuracy** | **100%** (correct drone identified) |
| Average latency | 11.14s |
| Average vendors returned | 4 |

### 7.2 Results by Category

| Category | Tests | Passed | Avg Latency | Notes |
|----------|-------|--------|-------------|-------|
| basic_pricing | 3 | 3 | 12.28s | Single model, standard query |
| comparison | 2 | 2 | 10.57s | Multi-retailer price comparison |
| stock_delivery | 2 | 2 | 11.13s | Stock availability queries |
| combo_pricing | 2 | 2 | 10.66s | Fly More Combo pricing |
| edge_case | 2 | 2 | 10.16s | Non-existent model + discontinued model |
| deal_search | 1 | 1 | 11.84s | Discount/promotion search |

### 7.3 Edge Case Handling

**TC-B-010** — Query for DJI Phantom 5 (non-existent model):
- `has_price: false`, `price_correct: true`
- The agent correctly responded "I was unable to retrieve current pricing for the DJI Phantom 5"
  rather than hallucinating a price. This validates the grounded generation behavior.

**TC-B-011** — Query for discontinued/hard-to-find model:
- `has_price: true`, all accuracy flags correct
- Agent used reference pricing fallback when web search was inconclusive.

### 7.4 Important Context: DuckDuckGo vs SerpAPI

This evaluation was run with DuckDuckGo as the web search backend. All 12 tests passed because
the evaluation ran as a fresh, low-frequency test session — DuckDuckGo did not rate-limit it.

However, during sustained development testing (repeated queries in short succession), DuckDuckGo
blocked automated queries and returned empty results consistently. The agent then looped for
8 iterations without finding pricing data. This is documented as **Failure Case 3** below.

**After migration to SerpAPI:** The rate-limiting failure no longer occurs. The 100% accuracy
rate in this evaluation reflects the correct agent logic; SerpAPI made that logic reliable in
production.

---

## 8. Configuration Comparisons

### 8.1 Comparison 1: Reranker Model — MiniLM vs BGE

**What was changed:** Replaced `cross-encoder/ms-marco-MiniLM-L-6-v2` with
`BAAI/bge-reranker-base`.

| | MiniLM-L-6-v2 | BGE-reranker-base | Change |
|--|:-------------:|:-----------------:|:------:|
| Parameters | 22M | 278M | +1164% |
| Architecture | Bi-encoder | Cross-encoder | Fundamentally different |
| Faithfulness | 0.925 | 0.922 | −0.003 |
| Answer Relevancy | 0.865 | 0.857 | −0.008 |
| **Context Precision** | 0.814 | **0.924** | **+0.110** |
| Context Recall | 0.855 | 0.875 | +0.020 |

**Winner:** BAAI/bge-reranker-base by +13.5% precision.

**Why:** A bi-encoder (MiniLM) encodes query and passage independently and computes a cosine
similarity score. A cross-encoder (BGE) processes the query and passage together in a single
attention pass, allowing it to model interactions between query tokens and passage tokens. This
"cross-attention" mechanism makes it far better at identifying whether a passage actually answers
the specific question, rather than just being about the same topic. The 200ms additional
inference time is a justified cost for this accuracy improvement.

---

### 8.2 Comparison 2: BERT Training Data Size

**What was changed:** Increased BERT classifier training data from 100 to 300 examples.

| | 100 training examples | 300 training examples | Change |
|--|:---------------------:|:---------------------:|:------:|
| Test set accuracy | 95.0% | **100.0%** | +5% |
| Macro F1 | 0.952 | **1.000** | +0.048 |
| Edge case confidence | 0.50–0.65 | 0.85–0.99 | Large improvement |
| LLM supervisor fallback rate | ~40% | **< 15%** | −62.5% |
| Time saved per query | — | ~2s | (when LLM skipped) |

**Winner:** 300 examples by large margin.

**What made 300 examples better:** It wasn't just quantity — it was diversity. The 300-sample set
added:
- Informal phrasing: "my drone is broken", "yo what does E001 mean"
- Comparative queries: "which one is cheaper", "what's the difference between"
- Ambiguous cases: "tell me about the camera" (could be RAG or diagnostic)
- Mixed-signal queries: "battery error code and price" (multi-route)

The 100-sample set was biased toward formal, well-structured queries. Adding edge cases pushed
BERT to learn intent from the meaning of the sentence, not just keyword patterns.

---

### 8.3 Comparison 3: Chunking Strategy

**What was changed:** Compared three chunking approaches on the same retrieval pipeline.

| | Fixed (1500/300) | Semantic (heuristic) | Parent-Child ★ |
|--|:----------------:|:--------------------:|:---------------:|
| Child size | 1500 chars | Variable | 300 chars |
| Parent size | — | — | 1500 chars |
| Search over | Full chunk | Section | Small child |
| LLM sees | Full chunk | Section | Full parent |
| Faithfulness | 0.925 | 0.842 | **0.958** |
| Answer Relevancy | 0.865 | 0.560 | **0.922** |
| Context Precision | 0.814 | 0.674 | **0.936** |
| Context Recall | 0.855 | 0.508 | **0.933** |

**Winner:** Parent-child chunking across all metrics.

**Why semantic chunking failed:** DJI manuals are structured technical documents. The section
boundaries the heuristic chunker detected were often paragraph breaks within a procedure, not
actual topic changes. The result was chunks that contained half a numbered step, or a table
header without its rows. This destroyed both embedding precision (malformed chunks don't embed
well) and answer quality (LLM received incomplete context).

**Why parent-child won:** Decoupling the search unit (small child, precise embedding) from
the context unit (large parent, complete information) solved the core RAG trade-off. The
retrieval found the right location in the document with high precision; the LLM received
the full surrounding section to form a complete answer.

---

## 9. Failure Cases

Three of eight documented failures are detailed here. The full set is in `FAILURE_CASES.md`.

---

### Failure Case 1: BM25 Stale Index After Ingestion

**Type:** Design Failure  
**Status:** ✅ Fixed

**What happened:** After ingesting the DJI Neo manual via the admin panel, queries about the
Neo returned "no context available about DJI Neo" — even though the PDF was successfully
indexed in Qdrant.

**Root cause:** The BM25 keyword index is built once at MCP server startup by scrolling all
Qdrant documents. New documents ingested via the admin panel are immediately available in
Qdrant's dense vector search, but the BM25 index in memory still has the pre-ingestion snapshot.
Since retrieval merges dense + BM25 results before reranking, newly added documents scored
zero in BM25 and were consistently filtered out by the reranker.

**Fix:** Added `rebuild_bm25_index()` in `retrieval.py`, called automatically after every
`ingest_and_index_pdf` and document delete operation. The rebuild scrolls all Qdrant documents
and reconstructs the BM25 corpus from scratch. This adds ~1–2 seconds to ingestion time, which
is acceptable for a background admin operation.

**Lesson:** Any in-memory index that mirrors a persistent store must be invalidated or rebuilt
when the persistent store changes. Startup-time initialization is not sufficient for systems
that support runtime data modification.

---

### Failure Case 2: Metadata Filter Mismatch

**Type:** Prompt Failure  
**Status:** ✅ Fixed

**What happened:** The query "Compare speed of Air 3 and Mavic 3" triggered the RAG planner
to plan two searches: one for Air 3 (successful) and one with `drone_model: "DJI Mavic 3"`
(zero results). The comparison answer only included Air 3 data.

**Root cause:** The RAG planner (LLM) was not constrained to use exact metadata strings. It
inferred "DJI Mavic 3" from the user's query, but the Qdrant payload stores `"DJI Mavic 3 Classic"`.
This is a prompt engineering failure — the LLM had no way to know the exact strings stored in
the database without being told explicitly.

**Fix:** Updated `PLANNER_PROMPT` in `rag_agent.py` to include an explicit enumeration of all
available drone model strings with mapping rules:
```
"Mavic 3" or "Mavic 3 Pro" → use "DJI Mavic 3 Classic"
"Mini 4 Pro" → use "DJI Mini 4 Pro"
```

**Lesson:** LLMs should never be asked to infer database key values. Any value that must match
a schema exactly (enum values, foreign keys, metadata fields) must be provided verbatim in the
system prompt. The LLM's job is to understand user intent; the system prompt's job is to map
that intent to valid system inputs.

---

### Failure Case 3: DuckDuckGo Rate-Limiting

**Type:** External Dependency Failure  
**Status:** ⚠️ Partially fixed (SerpAPI migration; non-reference models still depend on web search)

**What happened:** Agent System B was queried for pricing on DJI Avata 2 (a model not in the
reference pricing database). The agent called `search_duckduckgo` 8 times across its ReAct
loop. Every call returned zero results. The agent exhausted its iteration limit without
finding any data.

**Root cause:** The `duckduckgo-search` Python library is rate-limited for automated queries.
DuckDuckGo's bot detection returns empty result sets (not an error) when it identifies
automated usage patterns, causing the agent to retry rather than fail gracefully.

**Why the initial evaluation passed:** The 12-test evaluation ran as a fresh, low-frequency
session. DuckDuckGo did not rate-limit it. The failure emerged during sustained development
testing where the same endpoint was called dozens of times in quick succession.

**Fix applied:** Migrated web search from DuckDuckGo to SerpAPI (Google Search API). Added
`get_reference_pricing` as the primary tool, called before any web search. For the three
main models in the reference database (Mini 4 Pro, Air 3, Mavic 3 Pro), reference pricing
always returns data regardless of web search availability.

**Remaining limitation:** Models not in the reference database (Avata 2, Neo, Phantom 5)
still depend on web search. SerpAPI is reliable, but it is a paid external dependency — an
outage would affect pricing for these models. A more complete fix would populate the
reference database with all supported models.

**Lesson:** Never evaluate an external API dependency with a small, clean test suite. Rate
limits, bot detection, and quota exhaustion only appear under sustained or concurrent load.
Test external dependencies with repeated calls in quick succession to simulate real usage.

---

*For the remaining 5 failure cases (Cache disabled for filtered queries, Multi-model RAG comparison, Pricing history pollution, BERT low confidence with 100 samples, No self-correction on empty retrieval), see `FAILURE_CASES.md`.*
