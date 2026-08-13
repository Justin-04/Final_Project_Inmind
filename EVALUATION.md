# DJI RAG System - Evaluation Framework

## Overview

This document defines quantitative metrics, qualitative measures, and evaluation procedures for the Multi-Agent DJI Drone RAG System.

## 1. Quantitative Metrics

### 1.1 Latency Metrics
- **p50 (Median):** Target <500ms
- **p95:** Target <1500ms
- **p99:** Target <2000ms
- **Measurement:** End-to-end response time from request receipt to first chunk streamed

### 1.2 Token Cost Metrics
- **Input Tokens:** Tracked per query per agent
- **Output Tokens:** Tracked per response per agent
- **Cost Attribution:** LangSmith-tracked token spend by agent type and intent category
- **Budget Target:** <2000 tokens per query (avg)

### 1.3 Vector Search Metrics
- **Recall@5:** % of relevant documents in top-5 results (ground truth labeled)
- **Recall@10:** % of relevant documents in top-10 results
- **Precision@5:** % of top-5 results that are relevant
- **NDCG (Normalized Discounted Cumulative Gain):** Ranking quality
- **Target:** Recall@5 >85%, Precision@5 >80%

### 1.4 Intent Classification Accuracy
- **Precision by Intent:** Accuracy per intent category (DIAGNOSTIC, RAG, PRICING, GENERAL)
- **Recall by Intent:** Coverage per intent category
- **Macro F1:** Average F1 across intents
- **Target:** Macro F1 >0.90

### 1.5 Error Resolution Rate
- **Definition:** % of diagnostic queries that yield actionable resolution steps
- **Measurement:** Manual review of 50+ queries post-response
- **Target:** >85% actionable rate

### 1.6 Vendor Pricing Confidence
- **Definition:** % of pricing responses with system confidence score >0.8
- **Measurement:** Confidence histogram across 100+ pricing queries
- **Target:** >75% high-confidence pricing

### 1.7 Hallucination Rate
- **Definition:** % of outputs containing unsourced claims or factually incorrect info
- **Measurement:** Manual review of 100+ responses
- **Target:** <5% hallucination rate

---

## 2. Qualitative Metrics

### 2.1 User Satisfaction (CSAT)
- **Scale:** 1-5 (Very Unsatisfied to Very Satisfied)
- **Measurement:** Post-interaction survey
- **Target:** >4.0 average CSAT

### 2.2 Source Attribution Accuracy
- **Definition:** % of outputs with correct source citations
- **Measurement:** Manual spot-check of 50+ responses
- **Target:** >95% correct attribution

### 2.3 Hallucination Detection
- **Definition:** Outputs must reference ground-truth documents
- **Measurement:** Spot-check against Qdrant metadata
- **Target:** 0 ungrounded claims in sample

### 2.4 Conversational Coherence
- **Definition:** Multi-turn dialogue maintains context and logical flow
- **Measurement:** Manual evaluation of 10+ conversation threads
- **Target:** >90% coherence rating

---

## 3. System Health Metrics

### 3.1 Service Availability
- **Target:** >99.5% uptime per service
- **Measurement:** Monitored via health check endpoints

### 3.2 Error Rate by Category
- **MCP Tool Failures:** <0.5% failure rate
- **Vector DB Unavailability:** <0.1% failure rate
- **Agent Timeout:** <1% of queries exceed max iteration limit (5)
- **S3 Upload Failures:** <0.1% failure rate

### 3.3 Queue & Concurrency
- **Max Concurrent Requests:** 100+ simultaneous queries
- **Request Queue Depth:** Monitor for bottlenecks
- **Target:** <100ms average queue wait time

---

## 4. Evaluation Procedures

### 4.1 Ground Truth Dataset
**File:** `data/ground_truth_qa.json`

```json
{
  "test_cases": [
    {
      "query": "What are common compass calibration errors for Mini 4 Pro?",
      "drone_model": "mini_4_pro",
      "intent": "diagnostic",
      "expected_error_codes": ["E001", "E002"],
      "relevant_manual_pages": [42, 43, 51],
      "expected_pricing": null
    }
  ]
}
```

### 4.2 RAGAS Evaluation
- **Tools:** RAGAS (Retrieval-Augmented Generation Assessment)
- **Metrics Computed:**
  - Faithfulness (hallucination detection)
  - Answer Relevance
  - Context Precision / Recall
  - Aspect Critique
- **Frequency:** Weekly evaluation run
- **Script:** `scripts/run_evaluation.py`

### 4.3 Manual Spot-Checks
- **Frequency:** Daily spot-check of 5-10 queries
- **Criteria:**
  - Hallucination presence
  - Source attribution correctness
  - Conversational coherence
  - Pricing confidence vs. accuracy

### 4.4 Routing Accuracy
- **Definition:** % of queries routed to correct specialist agent
- **Measurement:** Compare BERT intent classification vs. human-labeled intents
- **Script:** `scripts/run_evaluation.py`
- **Target:** >92% routing accuracy

---

## 5. LangSmith Dashboard Configuration

### 5.1 Traces & Runs
- Enable tracing for all agent executions
- Tag runs by: intent_category, drone_model, user_id
- Track latency breakdowns per agent

### 5.2 Feedback & Annotations
- Collect user feedback scores post-interaction
- Flag hallucinations for retraining
- Annotate misdirected routing decisions

### 5.3 Cost Analysis
- Token spend dashboard by agent type
- Identify cost outliers (e.g., overly long contexts)
- Monthly cost trends

### 5.4 Latency Heatmaps
- Response time by intent category
- Response time by drone model (complex queries slower?)
- Peak hour analysis

---

## 6. Evaluation Cadence

| Metric | Frequency | Responsibility |
|--------|-----------|-----------------|
| p50/p95/p99 Latency | Real-time (LangSmith) | Automated |
| Token Cost | Daily | LangSmith dashboard |
| Vector Search Metrics | Weekly | `run_evaluation.py` |
| Intent Classification Accuracy | Weekly | `run_evaluation.py` |
| Hallucination Rate | Weekly | Manual + RAGAS |
| User CSAT | Ongoing | Post-interaction survey |
| Service Health | Real-time | Health check endpoints |
| Error Rate | Daily | Log analysis |

---

## 7. Success Criteria (MVP)

### 7.1 Must-Have
- ✓ p95 latency <1500ms
- ✓ Intent classification F1 >0.90
- ✓ Hallucination rate <5%
- ✓ Source attribution >95% accurate
- ✓ Vector search recall@5 >85%

### 7.2 Should-Have
- ✓ CSAT >4.0
- ✓ Pricing confidence >75% high-confidence
- ✓ Error resolution rate >85%
- ✓ Service availability >99.5%

### 7.3 Nice-to-Have
- ✓ Multi-turn coherence >90%
- ✓ Cost per query <0.05 USD
- ✓ Support for 50+ drone models

---

## 8. Running Evaluations

```bash
# Full RAGAS + routing evaluation
python scripts/run_evaluation.py --mode full

# Quick latency benchmark
python scripts/run_evaluation.py --mode latency

# Hallucination detection only
python scripts/run_evaluation.py --mode hallucination

# Generate LangSmith report
python scripts/run_evaluation.py --mode langsmith
```

---

## 9. Continuous Improvement

- Weekly sync to review LangSmith metrics
- Retrain BERT classifier if routing accuracy drops <90%
- Fine-tune summarizer if hallucination rate exceeds 5%
- Expand vector DB if search recall drops <80%
- Adjust max iteration limit if timeout rate exceeds 2%
