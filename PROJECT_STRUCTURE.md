# DJI Drone Multi-Agent RAG System - Project Structure

## Complete Directory Layout

```
dji-drone-multiagent/
├── .env.example                              # Environment template
├── .gitignore                                # Git ignore rules
├── README.md                                 # Project overview
├── context.md                                # Master specification (SINGLE SOURCE OF TRUTH)
├── EVALUATION.md                             # Evaluation framework & metrics
├── docker-compose.yml                        # 5-container orchestration
├── PROJECT_STRUCTURE.md                      # This file
│
├── data/                                     # Domain data & datasets
│   ├── manuals/
│   │   └── .gitkeep                         # Raw DJI manual PDFs go here
│   ├── images/
│   │   └── .gitkeep                         # Local diagram image cache
│   ├── ground_truth_qa.json                 # Ground truth QA pairs for evaluation
│   └── error_codes.json                     # DJI error code database
│
├── models/                                   # ML artifacts
│   └── bert_intent_classifier/
│       └── .gitkeep                         # Fine-tuned BERT weights
│
├── services/                                 # 5 Container Microservices
│   │
│   ├── agent-system-a/                      # CONTAINER 1: LangGraph Orchestrator
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── main.py                          # FastAPI entry point
│   │   └── src/
│   │       ├── __init__.py
│   │       ├── config.py                    # Configuration management
│   │       ├── pipeline/
│   │       │   ├── __init__.py
│   │       │   ├── input_guard.py           # Step 1: Input validation
│   │       │   ├── bert_tool.py             # Step 2: Intent classification
│   │       │   ├── supervisor.py            # Step 3: LangGraph orchestration
│   │       │   └── output_guard.py          # Step 5: Output validation
│   │       ├── agents/
│   │       │   ├── __init__.py
│   │       │   ├── rag_agent.py             # Specialist: RAG/Vector search
│   │       │   ├── diagnostic.py            # Specialist: Error resolution
│   │       │   └── summarizer.py            # Specialist: Response synthesis
│   │       └── clients/
│   │           ├── __init__.py
│   │           ├── mcp_client.py            # MCP server HTTP client
│   │           └── system_b_client.py       # System B A2A client
│   │
│   ├── agent-system-b/                      # CONTAINER 2: Vendor/Pricing Service
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── main.py                          # FastAPI entry point
│   │   └── src/
│   │       ├── __init__.py
│   │       └── vendor_agent.py              # Vendor search & pricing logic
│   │
│   ├── mcp-server/                          # CONTAINER 3: MCP Tool Executor
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── server.py                        # FastMCP entry point
│   │   └── tools/
│   │       ├── __init__.py
│   │       ├── qdrant_rag_tool.py           # Tool 1: Vector search
│   │       ├── error_code_tool.py           # Tool 2: Error DB lookup
│   │       ├── ingest_tool.py               # Tool 3: PDF ingestion
│   │       └── s3_helper.py                 # S3 upload helper
│   │
│   └── whisper-stt-service/                 # CONTAINER 5: Speech-to-Text
│       ├── Dockerfile
│       ├── requirements.txt
│       ├── main.py                          # FastAPI + WebSocket entry
│       └── stt_engine.py                    # faster-whisper handler
│
├── scripts/                                  # Automation & testing
│   ├── ingest_manuals.py                    # Manual PDF ingestion script
│   ├── train_bert_classifier.py             # BERT fine-tuning script
│   └── run_evaluation.py                    # RAGAS + evaluation suite
│
└── results/                                  # Evaluation results (generated)
    └── evaluation_*.json
```

---

## Service Topology (Docker Compose)

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (React/Next.js)                 │
│         HTTP REST + WebSocket + SSE Streaming              │
└──────────────┬──────────────────────────────────────────────┘
               │
       ┌───────┴────────┐
       │                │
┌──────▼──────┐   ┌────▼─────────┐
│ agent-      │   │whisper-stt-  │  (CONTAINER 5)
│system-a     │   │service        │  Port 9000
│(Port 8000)  │   │(faster-       │
│(CONTAINER 1)│   │whisper STT)   │
└──────┬──────┘   └────┬─────────┘
       │                │
       └───────┬────────┘
               │ (HTTP)
      ┌────────▼────────┐
      │  mcp-server     │  (CONTAINER 3)
      │  (FastMCP)      │  Port 5000
      │  Port 5000      │
      └────────┬────────┘
               │
       ┌───────┴────────────┐
       │                    │ (HTTP)
┌──────▼──────┐   ┌────────▼──────┐
│vector-db    │   │agent-system-b  │  (CONTAINER 2)
│(Qdrant)     │   │(Vendor/Pricing)│  Port 8001
│Port 6333    │   │                │
└─────────────┘   └────────────────┘
(CONTAINER 4)
```

---

## Pipeline Execution Flow (agent-system-a)

```
[User Query]
    ↓
[Input Guardrail] (src/pipeline/input_guard.py)
    ├─ Content policy enforcement
    ├─ Input length validation
    └─ Rate limiting
    ↓
[BERT Intent Classifier] (src/pipeline/bert_tool.py)
    ├─ Intent: diagnostic, rag, pricing, general
    └─ Confidence threshold: >0.7
    ↓
[Supervisor Agent] (src/pipeline/supervisor.py)
    ├─ Route to specialist agents
    ├─ Manage iteration bounds (max 5)
    └─ Track conversation history
    ↓
[Specialist Agents] (src/agents/) - Parallel or Sequential
    ├─ RAG Agent: MCP query_dji_manual_vector_db
    ├─ Diagnostic Agent: MCP lookup_dji_error_code_db
    └─ Pricing Agent: HTTP to agent-system-b
    ↓
[Summarizer Agent] (src/agents/summarizer.py)
    ├─ Aggregate results
    ├─ Embed S3 image URLs
    └─ Format as Markdown
    ↓
[Output Guardrail] (src/pipeline/output_guard.py)
    ├─ Hallucination detection
    ├─ Confidence scoring
    └─ Markdown safety
    ↓
[SSE Streaming Response]
```

---

## MCP Tools (mcp-server/tools/)

### Tool 1: query_dji_manual_vector_db
**Location:** `mcp-server/tools/qdrant_rag_tool.py`
- **Input:** query, drone_model, top_k
- **Output:** Top-k chunks with S3 URLs
- **Logic:** Hybrid vector search (dense + BM25) with metadata filtering

### Tool 2: lookup_dji_error_code_db
**Location:** `mcp-server/tools/error_code_tool.py`
- **Input:** error_code
- **Output:** Description, resolution steps, severity
- **Logic:** Exact lookup against data/error_codes.json

### Tool 3: ingest_and_index_pdf
**Location:** `mcp-server/tools/ingest_tool.py`
- **Input:** pdf_file, drone_model, source_name
- **Output:** Indexed chunks count, extracted images count, vector IDs
- **Logic:** PDF parse → text chunk → image S3 upload → Qdrant index

---

## Configuration Files

### .env.example
Template for all environment variables:
- AWS credentials
- LangSmith API key
- OpenAI API key
- Service URLs (internal Docker network)

### docker-compose.yml
Orchestrates 5 containers:
1. agent-system-a (Port 8000)
2. agent-system-b (Port 8001)
3. mcp-server (Port 5000)
4. whisper-stt-service (Port 9000)
5. vector-db / Qdrant (Port 6333)

All services communicate over `dji-rag-network` bridge.

---

## Key Files Summary

| File | Purpose | Status |
|------|---------|--------|
| context.md | Master specification | ✓ Complete |
| EVALUATION.md | Metrics & evaluation | ✓ Complete |
| docker-compose.yml | 5-container setup | ✓ Complete |
| agent-system-a/main.py | FastAPI orchestrator | ✓ Scaffolded |
| agent-system-a/src/pipeline/* | Pipeline stages | ✓ Scaffolded |
| agent-system-a/src/agents/* | Specialist agents | ✓ Scaffolded |
| mcp-server/tools/* | MCP tool implementations | ✓ Scaffolded |
| scripts/run_evaluation.py | Evaluation suite | ✓ Scaffolded |

---

## Next Implementation Steps

1. **LangGraph Integration** - Connect supervisor.py to LangGraph state machine
2. **Vector DB Setup** - Initialize Qdrant collection schema
3. **MCP Tools** - Implement hybrid search, error lookup, PDF ingestion
4. **BERT Fine-tuning** - Train intent classifier on ground_truth_qa.json
5. **LangSmith Tracing** - Wire tracing into all agent executions
6. **Integration Tests** - End-to-end pipeline tests
7. **Deployment** - Docker Compose build and deployment
