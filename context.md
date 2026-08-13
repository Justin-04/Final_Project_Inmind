# Multi-Agent DJI Drone RAG System - Project Context

## 1. EXECUTIVE SUMMARY & VISION

**System Purpose:**
Enterprise-grade, distributed Multi-Agent RAG System for DJI Drone Maintenance, Diagnostics, Specs, and Purchasing.

**Target Use Cases:**
- Domain-specific conversational assistance for DJI drone models (Mini 4 Pro, Air 3, Mavic 3 Pro, etc.)
- Multimodal RAG combining text + PDF diagrams and schematics
- Live error code troubleshooting with contextual resolution
- Real-time vendor pricing and parts purchasing information
- Dynamic PDF ingestion through secure Admin portal

**Core Capabilities:**
- Intent-driven conversation routing via Fine-Tuned BERT classifier
- Multi-turn dialogue with supervisor state management (max 5 iteration loops)
- Streaming SSE responses with markdown rendering
- Voice-to-text transcription via Whisper
- Hybrid vector search with metadata filtering (drone model awareness)
- Automatic diagram extraction and S3 indexing from PDFs
- Vendor pricing integration via third-party API microservice
- Native LangSmith tracing for cost, latency, and accuracy metrics

---

## 2. SYSTEM ARCHITECTURE & CONTAINER LAYOUT

### **5-Container Microservice Orchestration (Docker Compose)**

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (React/Next.js)                 │
│         HTTP REST + WebSocket + SSE Streaming              │
└──────────────┬──────────────────────────────────────────────┘
               │
       ┌───────┴────────┐
       │                │
┌──────▼──────┐   ┌────▼─────────┐
│ agent-      │   │whisper-stt-  │
│system-a     │   │service        │
│(LangGraph)  │   │(FastAPI)      │
└──────┬──────┘   └────┬─────────┘
       │                │
       └───────┬────────┘
               │
      ┌────────▼────────┐
      │  mcp-server     │
      │  (FastMCP)      │
      └────────┬────────┘
               │
       ┌───────┴────────┐
       │                │
┌──────▼──────┐   ┌────▼──────────┐
│vector-db    │   │agent-system-b  │
│(Qdrant)     │   │(Vendor/Pricing)│
└─────────────┘   └────────────────┘
```

### **Container Specifications**

#### **1. agent-system-a (LangGraph + FastAPI Orchestrator)**
- **Role:** Primary orchestration, conversation management, request routing
- **Technology Stack:** LangGraph, FastAPI, Pydantic, Python 3.11+
- **Port:** 8000
- **Pipeline Execution Flow:**
  ```
  [Input Request]
    ↓
  [Input Guardrail - Content Safety Check]
    ↓
  [Fine-Tuned BERT Intent Classifier]
    ↓
  [Supervisor Agent - State & Routing]
    ↓
  [Specialist Agents] (Parallel or Sequential)
    ├─ RAG Agent (Vector search + context retrieval)
    ├─ Diagnostic Agent (Error code resolution)
    └─ Pricing Agent (Vendor integration via A2A HTTP)
    ↓
  [Summarizer/Generator Agent]
    ↓
  [Output Guardrail - Validation]
    ↓
  [Streamed Response (SSE)]
  ```

- **Internal Agents:**
  - **Supervisor Agent:** Manages conversation state, history tracking, iteration bounds (max 5 loops), error handling, and task routing decisions
  - **RAG Agent:** Executes MCP tool `query_dji_manual_vector_db` for spec/hardware retrieval with drone_model metadata filtering
  - **Diagnostic Agent:** Executes MCP tool `lookup_dji_error_code_db` for structured error resolution with actionable remediation steps
  - **Pricing Agent:** Makes HTTP network calls to agent-system-b (never direct Python imports)
  - **Summarizer Agent:** Synthesizes multi-agent outputs into coherent Markdown with S3 image URL rendering

- **Core Endpoints:**
  - `POST /api/v1/chat` - Text input, SSE streaming response
  - `POST /api/v1/admin/ingest` - PDF ingestion + indexing trigger
  - `GET /health` - Health check for load balancer

- **Dependencies:** langchain, langgraph, pydantic, httpx, boto3, qdrant-client, bert-for-tf2

#### **2. agent-system-b (Vendor & Pricing Microservice)**
- **Role:** Third-party vendor data aggregation and pricing breakdown
- **Technology Stack:** FastAPI, Python 3.11+
- **Port:** 8001
- **Communication Protocol:** HTTP REST only (invoked via A2A from agent-system-a)
- **Core Endpoints:**
  - `POST /api/v1/vendor-search` - Query vendors by drone model + part category
  - `GET /api/v1/pricing/{part_id}` - Real-time pricing lookup
  - `GET /health` - Health check

- **Never imported as a Python package** — always HTTP network calls only

#### **3. mcp-server (FastMCP Tool Executor)**
- **Role:** Isolated microservice for MCP-compliant tool execution and orchestration
- **Technology Stack:** FastMCP, Python 3.11+
- **Port:** 5000
- **Exposed Tools:**
  - **query_dji_manual_vector_db:**
    - Input: query (text), drone_model (str), top_k (int)
    - Output: List[{text: str, metadata: {source, drone_model, page_num, s3_url}}]
    - Logic: Hybrid vector search (dense + BM25) against Qdrant with metadata filtering
  - **lookup_dji_error_code_db:**
    - Input: error_code (str)
    - Output: {code: str, description: str, resolution_steps: List[str], severity: str}
    - Logic: Exact lookup against structured error resolution dataset
  - **ingest_and_index_pdf:**
    - Input: pdf_file (bytes), drone_model (str), source_name (str)
    - Output: {indexed_chunks: int, extracted_images: int, vector_ids: List[str]}
    - Logic: PDF parsing → text chunking (512 tokens / 64 overlap) → image extraction to S3 → vector embedding → Qdrant indexing

#### **4. whisper-stt-service (Speech-to-Text)**
- **Role:** Real-time voice transcription microservice
- **Technology Stack:** FastAPI, faster-whisper, CTranslate2, Python 3.11+
- **Port:** 9000
- **Communication:** WebSocket + HTTP
- **WebSocket Endpoint:** `ws://localhost:9000/ws/transcribe`
  - Receives audio chunks (PCM or MP3 encoded)
  - Transcribes to text in real-time
  - Forwards transcript to `POST agent-system-a:8000/api/v1/chat`
- **HTTP Endpoint:** `POST /api/v1/transcribe` (single file upload)

#### **5. vector-db (Qdrant Vector Database)**
- **Role:** Persistent vector storage and semantic search
- **Technology Stack:** Qdrant (Docker image: qdrant/qdrant:latest)
- **Port:** 6333 (HTTP API), 6334 (gRPC)
- **Storage:** Mounted volume at `/qdrant/storage`
- **Collection Schema:**
  ```json
  {
    "name": "dji_manuals",
    "vectors": {
      "size": 1536,
      "distance": "Cosine"
    },
    "payload_schema": {
      "drone_model": "keyword",
      "source": "text",
      "page_num": "integer",
      "s3_url": "text",
      "chunk_index": "integer"
    }
  }
  ```

---

## 3. EXTERNAL SERVICE INTEGRATIONS

### **AWS Infrastructure**
- **S3 Bucket (dji-multimodal-rag-assets):**
  - Stores extracted manual schematics, diagrams, and images from PDF ingestion
  - Path structure: `s3://dji-multimodal-rag-assets/{drone_model}/{source_name}/images/{image_id}.png`
  - TTL and lifecycle policies for cost optimization

### **LangSmith Tracing**
- **Integration:** Native tracing via LangChain/LangGraph
- **Metrics Tracked:**
  - Per-query token costs (input + output)
  - Latency per agent (median, p95, p99)
  - Agent success/failure rates by intent category
  - Vector search recall and precision
  - End-to-end response time SLA tracking
- **Dashboard:** LangSmith cloud dashboard for observability

---

## 4. INPUT & OUTPUT SPECIFICATIONS

### **Input Guardrails**
- Content policy enforcement (no malicious payloads, jailbreaks, or OOD content)
- Input length validation (max 8192 tokens)
- Intent classification confidence threshold (>0.7 required)
- Rate limiting per user/API key

### **Output Guardrails**
- Hallucination detection (outputs must reference source documents)
- Confidence scoring on pricing data (only display if vendor_confidence > 0.8)
- Markdown safety (no script tags, XSS prevention)
- S3 URL validation before rendering

---

## 5. DATA FLOW EXAMPLE: USER QUERY

**Scenario:** User asks "What are the common error codes for DJI Mini 4 Pro when calibrating the compass?"

```
1. Frontend sends: {query, user_id, drone_model: "mini_4_pro"}
2. agent-system-a receives request
3. Input Guardrail validates request
4. BERT Intent Classifier determines: intent=DIAGNOSTIC, confidence=0.92
5. Supervisor Agent routes to Diagnostic Agent + RAG Agent (parallel)
6. Diagnostic Agent: calls MCP lookup_dji_error_code_db("COMPASS_CALIBRATION")
7. RAG Agent: calls MCP query_dji_manual_vector_db(
     query="compass calibration error codes mini 4 pro",
     drone_model="mini_4_pro",
     top_k=5
   )
8. Both agents return results
9. Summarizer Agent:
   - Aggregates error codes, resolution steps, and manual excerpts
   - Embeds S3 diagram URLs from metadata
   - Formats as Markdown with tables, bullets, and links
10. Output Guardrail validates and scores confidence
11. Response streamed via SSE to frontend
```

---

## 6. TOOL DEFINITIONS (MCP Tools)

### **Tool 1: query_dji_manual_vector_db**
```json
{
  "name": "query_dji_manual_vector_db",
  "description": "Hybrid vector search across DJI manual embeddings with drone model filtering",
  "input_schema": {
    "type": "object",
    "properties": {
      "query": {"type": "string", "description": "Natural language search query"},
      "drone_model": {"type": "string", "description": "Target drone model (e.g., mini_4_pro)"},
      "top_k": {"type": "integer", "description": "Number of results to return", "default": 5}
    },
    "required": ["query", "drone_model"]
  },
  "output_schema": {
    "type": "array",
    "items": {
      "type": "object",
      "properties": {
        "text": {"type": "string"},
        "metadata": {
          "drone_model": "string",
          "source": "string",
          "page_num": "integer",
          "s3_url": "string"
        },
        "similarity_score": {"type": "number"}
      }
    }
  }
}
```

### **Tool 2: lookup_dji_error_code_db**
```json
{
  "name": "lookup_dji_error_code_db",
  "description": "Look up DJI error codes with resolution steps and severity levels",
  "input_schema": {
    "type": "object",
    "properties": {
      "error_code": {"type": "string", "description": "DJI error code (e.g., E001, COMPASS_ERR)"}
    },
    "required": ["error_code"]
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "code": {"type": "string"},
      "description": {"type": "string"},
      "resolution_steps": {"type": "array", "items": {"type": "string"}},
      "severity": {"type": "string", "enum": ["critical", "warning", "info"]},
      "related_codes": {"type": "array", "items": {"type": "string"}}
    }
  }
}
```

### **Tool 3: ingest_and_index_pdf**
```json
{
  "name": "ingest_and_index_pdf",
  "description": "Admin tool: Parse PDF, extract images to S3, chunk text, and index vectors in Qdrant",
  "input_schema": {
    "type": "object",
    "properties": {
      "pdf_file": {"type": "string", "description": "PDF file path or bytes (base64)"},
      "drone_model": {"type": "string", "description": "Target drone model"},
      "source_name": {"type": "string", "description": "Human-readable source label"}
    },
    "required": ["pdf_file", "drone_model", "source_name"]
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "indexed_chunks": {"type": "integer"},
      "extracted_images": {"type": "integer"},
      "vector_ids": {"type": "array", "items": {"type": "string"}},
      "s3_paths": {"type": "array", "items": {"type": "string"}}
    }
  }
}
```

---

## 7. EVALUATION METRICS & OBSERVABILITY

### **Quantitative Metrics**
- **Latency (p50, p95, p99):** Target <2s for 95th percentile response time
- **Token Cost:** Track input + output tokens per agent per query
- **Vector Search Precision/Recall:** Validate against human-labeled ground truth
- **Error Resolution Rate:** % of diagnostic queries with actionable steps
- **Intent Classification Accuracy:** Precision/recall against labeled test set
- **Vendor Pricing Confidence:** % of pricing responses with confidence > 0.8

### **Qualitative Metrics**
- User satisfaction score (CSAT post-interaction)
- Hallucination rate (manual review sample)
- Source attribution accuracy (does output cite correct documents?)

### **LangSmith Dashboard**
- Real-time tracing of agent execution paths
- Cost breakdown by agent and intent category
- Latency heatmaps by time of day and query complexity
- Error rate tracking by error category

---

## 8. ENVIRONMENT CONFIGURATION

### **Docker Compose Services**
All services defined in `docker-compose.yml` at project root.

### **Environment Variables (.env)**
```
# AWS
AWS_ACCESS_KEY_ID=<your_key>
AWS_SECRET_ACCESS_KEY=<your_secret>
AWS_REGION=us-east-1
S3_BUCKET_NAME=dji-multimodal-rag-assets

# LangSmith
LANGSMITH_API_KEY=<your_key>
LANGSMITH_PROJECT=dji-rag-system

# OpenAI / LLM
OPENAI_API_KEY=<your_key>
OPENAI_MODEL=gpt-4

# Qdrant
QDRANT_URL=http://vector-db:6333
QDRANT_API_KEY=<optional>

# Service URLs
AGENT_B_URL=http://agent-system-b:8001
MCP_SERVER_URL=http://mcp-server:5000
WHISPER_URL=http://whisper-stt-service:9000
```

---

## 9. PROJECT INITIALIZATION CHECKLIST

- [ ] Docker Compose file created with all 5 services
- [ ] agent-system-a (FastAPI + LangGraph) scaffolded
- [ ] agent-system-b (Vendor microservice) scaffolded
- [ ] mcp-server (FastMCP tools) scaffolded
- [ ] whisper-stt-service scaffolded
- [ ] vector-db (Qdrant) volume and schema initialized
- [ ] Environment variable template (.env.example) created
- [ ] CI/CD pipeline (GitHub Actions) configured
- [ ] LangSmith integration configured
- [ ] AWS S3 bucket and IAM policies created
- [ ] Kubernetes manifests (optional for production)
- [ ] API documentation (OpenAPI/Swagger) generated
- [ ] Test suite scaffolded (unit, integration, e2e)

---

## 10. NEXT STEPS

1. Initialize directory structure with boilerplate files
2. Create docker-compose.yml with all service definitions
3. Scaffold FastAPI applications for each container
4. Set up LangGraph state machines for agent orchestration
5. Define MCP tool implementations in mcp-server
6. Configure AWS S3 and Qdrant
7. Implement input/output guardrails
8. Add LangSmith tracing hooks
9. Deploy and test end-to-end flow
