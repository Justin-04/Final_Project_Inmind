# Agent System A — Architecture & Implementation Summary

## Overview

Agent System A is the primary orchestrator of the DJI Drone RAG multi-agent system. Built with **LangGraph**, it coordinates multiple LLM-powered specialist agents to answer drone-related queries about manuals (RAG), diagnostics (error codes), and pricing (vendor comparison).

It serves as the single entry point for all user interactions, handling authentication, routing, caching, rate limiting, and response generation.

---

## System Architecture

```
                        ┌─────────────────────────────────────────────────────────┐
                        │                  AGENT SYSTEM A (port 8000)              │
                        │                                                         │
  User ──► [JWT Auth] ──► [Rate Limiter] ──► [Response Cache] ──► [LangGraph]    │
                        │                                                         │
                        │  LangGraph Pipeline:                                    │
                        │  ┌────────────┐                                         │
                        │  │Input Guard  │  (Prompt Guard — safety check)         │
                        │  └─────┬──────┘                                         │
                        │        │                                                │
                        │  ┌─────▼──────┐                                         │
                        │  │BERT Classif.│  (DistilBERT intent classifier)        │
                        │  └─────┬──────┘                                         │
                        │        │                                                │
                        │  ┌─────▼──────┐                                         │
                        │  │ Supervisor  │  (LLM routing if BERT < 0.85)          │
                        │  └─────┬──────┘                                         │
                        │     ┌──┼──────────┐                                     │
                        │     │  │          │                                     │
                        │  ┌──▼──▼──┐ ┌────▼────┐ ┌────────┐                     │
                        │  │RAG Agt │ │Diag Agt │ │Price Agt│                     │
                        │  └────┬───┘ └────┬────┘ └────┬───┘                     │
                        │       │          │           │                          │
                        │  ┌────▼──────────▼───────────▼──┐                      │
                        │  │         Summarizer            │                      │
                        │  └──────────────┬───────────────┘                      │
                        │                 │                                       │
                        │  ┌──────────────▼───────────────┐                      │
                        │  │        Output Guard           │                      │
                        │  └──────────────────────────────┘                      │
                        └─────────────────────────────────────────────────────────┘
                                    │                           │
                          HTTP to MCP Server            HTTP to Agent System B
                            (port 8002)                      (port 8001)
```

---

## Directory Structure

```
services/agent-system-a/
├── main.py                         # FastAPI app, endpoints, lifespan
├── requirements.txt
├── .env
└── src/
    ├── agents/
    │   ├── rag_agent.py            # LLM-powered RAG planner + MCP calls
    │   ├── diagnostic_agent.py     # LLM-powered error analysis + MCP calls
    │   ├── pricing_agent.py        # LLM-powered pricing + Agent-B calls
    │   └── summarizer.py           # LLM response synthesizer
    ├── auth/
    │   ├── routes.py               # /auth/login, /auth/register
    │   └── middleware.py           # JWT verification (get_current_user, require_admin)
    ├── db/
    │   └── conversation_store.py   # MongoDB persistence (Motor async driver)
    ├── graph/
    │   ├── workflow.py             # LangGraph definition (nodes + edges)
    │   └── nodes.py                # Thin wrappers connecting graph to agents
    ├── middleware/
    │   ├── rate_limiter.py         # Redis-based per-user rate limiting
    │   └── circuit_breaker.py      # Circuit breaker for external HTTP calls
    ├── pipeline/
    │   ├── input_guard.py          # LLM-based safety filter (v1)
    │   ├── input_guard_v2.py       # Prompt Guard model (Meta Llama)
    │   ├── classifier.py           # BERT intent classifier
    │   ├── supervisor.py           # LLM supervisor (fallback routing)
    │   ├── output_guard.py         # Output validation
    │   └── response_cache.py       # Redis semantic response cache
    └── state/
        └── agent_state.py          # TypedDict shared pipeline state
```

---

## Key Components

### 1. Request Flow (main.py)

1. **JWT Authentication** — All `/chat`, `/voice`, `/admin` endpoints require a valid JWT token. Public: `/health`, `/auth/*`.
2. **Rate Limiting** — Redis fixed-window counter, 20 requests per 60 seconds per user. Returns `429` when exceeded. Fail-open if Redis is unavailable.
3. **Response Cache** — Semantic cache (cosine similarity > 0.95 using `text-embedding-3-small`). If a near-identical query was answered before, returns cached response instantly. Skips caching for pricing queries (prices change).
4. **LangGraph Pipeline** — Full multi-agent execution.
5. **MongoDB Persistence** — Saves user + assistant messages per conversation. Loads last 4 messages as context for follow-up queries.

### 2. Input Guard (pipeline/input_guard_v2.py)

Uses **Meta Llama Prompt Guard 2** (22M params) to classify queries as safe or unsafe (jailbreak/injection detection). Runs locally on CPU in ~50ms. If the model is unavailable (gated access), falls back to v1 (LLM-based safety check).

### 3. BERT Intent Classifier (pipeline/classifier.py)

**DistilBERT** fine-tuned on 300 examples across 3 classes: `rag`, `diagnostic`, `pricing`.

- Accuracy: 100% on test set
- Inference: ~50ms on CPU
- Purpose: Fast pre-routing to skip the expensive LLM supervisor call

If confidence >= 0.85, the supervisor trusts BERT and routes directly. Below that, the LLM supervisor makes the final routing decision.

### 4. Supervisor (pipeline/supervisor.py)

LLM-based router (gpt-4o-mini) that analyzes the query when BERT is uncertain. Decides which specialist agent should handle the request. Supports an iteration counter to prevent infinite loops (max 5 iterations).

### 5. RAG Agent (agents/rag_agent.py)

**LLM-powered search planner** that:
1. Analyzes the query using gpt-4o-mini
2. Detects drone model(s) and plans the retrieval strategy
3. For comparisons, plans separate filtered searches per model
4. Calls MCP server's `query_dji_manual_vector_db` tool over HTTP
5. Returns merged chunks for the summarizer

Protected by the **MCP circuit breaker** — if the MCP server is down (3 consecutive failures), requests fail immediately with a graceful message instead of hanging.

### 6. Diagnostic Agent (agents/diagnostic_agent.py)

**LLM-powered troubleshooting agent** that:
1. Analyzes the error/symptom using gpt-4o-mini
2. Extracts error codes (E001, E003, etc.)
3. Plans actions: lookup codes + search manuals
4. Calls MCP server's `lookup_dji_error_code_db` and `query_dji_manual_vector_db`

Shares the same MCP circuit breaker as the RAG agent.

### 7. Pricing Agent (agents/pricing_agent.py)

**LLM-powered pricing planner** that:
1. Extracts drone model(s) from query + conversation history
2. Detects if single or multi-model comparison is needed
3. Calls **agent-system-b** over HTTP (`POST /v1/pricing`)
4. For multi-model: calls system-b once per model, merges vendor results

Protected by the **agent-system-b circuit breaker** — independent from the MCP breaker.

### 8. Summarizer (agents/summarizer.py)

Takes raw specialist outputs (chunks, error codes, vendor data) and synthesizes a user-facing response. Uses gpt-4o-mini with context-specific prompts. Also runs the output guard to strip any hallucinated content.

### 9. Response Cache (pipeline/response_cache.py)

**Redis semantic cache at the agent level:**
- Embeds incoming query with `text-embedding-3-small`
- Scans cached entries for cosine similarity > 0.95
- On HIT: returns cached response instantly (skips entire pipeline)
- On MISS: after pipeline completes, stores the response for future queries
- **Pricing queries are excluded** from caching (prices change over time)

### 10. Rate Limiter (middleware/rate_limiter.py)

**Redis fixed-window counter:**
- Key: `rate_limit:{user_id}`
- Limit: 20 requests per 60 seconds (configurable via env vars)
- On exceed: returns HTTP 429 with `Retry-After` header
- Fail-open: if Redis is down, all requests pass through (never blocks users due to infrastructure failure)

### 11. Circuit Breaker (middleware/circuit_breaker.py)

**Three-state pattern protecting external HTTP calls:**

```
CLOSED (normal) ──[3 consecutive failures]──► OPEN (fail-fast)
                                                    │
                                              [30s cooldown]
                                                    │
                                              HALF_OPEN (probe)
                                                    │
                                         success → CLOSED
                                         failure → OPEN
```

Two instances:
- `mcp_circuit_breaker` — protects all calls to MCP server (RAG + Diagnostic agents)
- `agent_b_circuit_breaker` — protects all calls to agent-system-b (Pricing agent)

When open, agents return graceful error messages. Status is visible at `/health`.

---

## Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | None | Health check + circuit breaker status |
| POST | `/api/v1/auth/register` | None | Register user (username, password, role) |
| POST | `/api/v1/auth/login` | None | Login, returns JWT |
| POST | `/api/v1/chat` | User | Main chat (rate-limited) |
| POST | `/api/v1/chat/stream` | User | SSE streaming chat (rate-limited) |
| POST | `/api/v1/voice` | User | Audio → Whisper → chat pipeline |
| POST | `/api/v1/voice/transcribe` | User | Audio → text only |
| GET | `/api/v1/conversations` | User | List conversations |
| GET | `/api/v1/conversations/{id}` | User | Get conversation messages |
| PUT | `/api/v1/conversations/{id}/rename` | User | Rename conversation |
| DELETE | `/api/v1/conversations/{id}` | User | Delete conversation |
| POST | `/api/v1/admin/ingest` | Admin | Ingest PDF into vector DB |
| GET | `/api/v1/admin/documents` | Admin | List ingested documents |
| DELETE | `/api/v1/admin/documents/{name}` | Admin | Delete document from vector DB |

---

## External Dependencies

| Service | URL | Purpose |
|---------|-----|---------|
| MCP Server | `http://localhost:8002` | Vector search, error codes, PDF ingestion |
| Agent System B | `http://localhost:8001` | Pricing research (LLM + web search) |
| MongoDB | `mongodb://localhost:27017` | Conversation + user persistence |
| Redis | `redis://localhost:6380` | Response cache + rate limiting |
| OpenAI API | cloud | Embeddings, LLM calls, Whisper STT |

---

## Design Patterns Used

| Pattern | Where | Purpose |
|---------|-------|---------|
| **Multi-Agent Orchestration** | LangGraph pipeline | Coordinate specialist agents |
| **Router Pattern** | BERT + LLM Supervisor | Fast routing with fallback |
| **ReAct (Reason+Act)** | Agent System B | LLM tool-calling loop |
| **Fan-out/Fan-in** | RAG comparison queries | Parallel searches, merged results |
| **Circuit Breaker** | HTTP calls to MCP/Agent-B | Graceful degradation |
| **Semantic Caching** | Two tiers (agent + MCP) | Reduce latency + API costs |
| **Rate Limiting** | Redis token bucket | Prevent abuse |
| **Guardrails** | Input + Output guards | Safety filtering |
| **JWT Authentication** | Auth middleware | Role-based access control |

---

## Caching Strategy (Two-Tier)

```
User query
    │
    ▼
[Agent-Level Cache (cosine > 0.95)]
    │ HIT → return instantly (skip everything)
    │ MISS ↓
    │
[Full Pipeline: guard → classifier → supervisor → agent]
    │
    │ agent calls MCP ──► [MCP Chunk Cache (cosine > 0.90)]
    │                         │ HIT → skip retrieval+rerank
    │                         │ MISS → full retrieval
    │
    ▼
[Summarizer → Output Guard → Response]
    │
    ▼
[Store in Agent-Level Cache (unless pricing)]
```

- **Agent cache**: catches identical/near-identical full user queries
- **MCP cache**: catches when the RAG planner produces similar search terms despite different user phrasing

---

## Configuration (Environment Variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | — | OpenAI API key |
| `MCP_SERVER_URL` | `http://localhost:8002` | MCP server base URL |
| `AGENT_B_URL` | `http://localhost:8001` | Agent system B base URL |
| `MONGODB_URI` | — | MongoDB connection string |
| `REDIS_URL` | `redis://localhost:6380` | Redis for caching + rate limiting |
| `BERT_MODEL_PATH` | — | Path to fine-tuned BERT classifier |
| `RATE_LIMIT_REQUESTS` | `20` | Max requests per window |
| `RATE_LIMIT_WINDOW` | `60` | Window size in seconds |
| `LANGFUSE_SECRET_KEY` | — | Langfuse tracing (optional) |
| `LANGFUSE_PUBLIC_KEY` | — | Langfuse tracing (optional) |
| `LANGFUSE_BASE_URL` | — | Self-hosted Langfuse URL |
