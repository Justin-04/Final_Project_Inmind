# DJI Multi-Agent RAG System - Initialization Checklist

## ✅ Project Structure Initialization - COMPLETE

### Directory Structure
- [x] Root project files (.env.example, .gitignore, README.md, docker-compose.yml)
- [x] context.md (Master specification - 10 sections)
- [x] EVALUATION.md (Comprehensive metrics framework)
- [x] data/ directory with ground_truth_qa.json and error_codes.json
- [x] models/ directory for BERT artifacts
- [x] scripts/ directory with 3 automation scripts

### Service Scaffolding (5 Containers)
- [x] agent-system-a (LangGraph orchestrator)
  - [x] Dockerfile, requirements.txt, main.py
  - [x] src/config.py (configuration management)
  - [x] src/pipeline/ (5-stage pipeline scaffolding)
  - [x] src/agents/ (specialist agents scaffolding)
  - [x] src/clients/ (HTTP clients for MCP and System B)

- [x] agent-system-b (Vendor/pricing service)
  - [x] Dockerfile, requirements.txt, main.py
  - [x] src/vendor_agent.py

- [x] mcp-server (MCP tool executor)
  - [x] Dockerfile, requirements.txt, server.py
  - [x] tools/qdrant_rag_tool.py (Vector search)
  - [x] tools/error_code_tool.py (Error lookup)
  - [x] tools/ingest_tool.py (PDF ingestion)
  - [x] tools/s3_helper.py (S3 upload helper)

- [x] whisper-stt-service (Speech-to-text)
  - [x] Dockerfile, requirements.txt, main.py
  - [x] stt_engine.py (faster-whisper handler)

### Scripts & Automation
- [x] scripts/ingest_manuals.py (PDF ingestion automation)
- [x] scripts/train_bert_classifier.py (BERT fine-tuning)
- [x] scripts/run_evaluation.py (RAGAS + evaluation suite)

---

## 📋 Pre-Implementation Setup

### Environment Configuration
- [ ] Copy .env.example to .env
- [ ] Fill in AWS credentials (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
- [ ] Fill in OpenAI API key (OPENAI_API_KEY)
- [ ] Fill in LangSmith API key (LANGSMITH_API_KEY)
- [ ] Set S3 bucket name (S3_BUCKET_NAME)

### AWS Infrastructure
- [ ] Create S3 bucket: dji-multimodal-rag-assets
- [ ] Set up IAM user with S3 access
- [ ] Configure bucket lifecycle policies
- [ ] Enable versioning (optional)

### Qdrant Setup
- [ ] Initialize Qdrant collection: "dji_manuals"
- [ ] Set vector size: 1536 (for sentence-transformers embeddings)
- [ ] Configure metadata schema (drone_model, source, page_num, s3_url)

---

## 🔧 Implementation Phases

### Phase 1: LangGraph Integration
- [ ] Implement LangGraph state machine in supervisor.py
- [ ] Wire agent routing logic
- [ ] Set up iteration management
- [ ] Connect to agent execution callbacks

### Phase 2: Vector Database Setup
- [ ] Initialize Qdrant Python client
- [ ] Create collection with proper schema
- [ ] Test vector insert/search operations
- [ ] Implement hybrid search (dense + BM25)

### Phase 3: MCP Tools Implementation
- [ ] Implement query_dji_manual_vector_db
  - [ ] Sentence-transformer embeddings
  - [ ] Qdrant hybrid search
  - [ ] Metadata filtering by drone_model
  - [ ] Return top-k with S3 URLs
  
- [ ] Implement lookup_dji_error_code_db
  - [ ] Load error_codes.json
  - [ ] Exact string matching
  - [ ] Return resolution steps
  
- [ ] Implement ingest_and_index_pdf
  - [ ] PDF parsing (PyPDF2)
  - [ ] Image extraction
  - [ ] Text chunking (512 tokens / 64 overlap)
  - [ ] S3 upload with proper paths
  - [ ] Vector embedding and Qdrant indexing

### Phase 4: BERT Intent Classification
- [ ] Load pre-trained BERT model
- [ ] Prepare training dataset from ground_truth_qa.json
- [ ] Fine-tune on DJI-domain intents
- [ ] Evaluate accuracy (target: >0.90 F1)
- [ ] Save model to models/bert_intent_classifier/

### Phase 5: Input & Output Guardrails
- [ ] Implement input_guard.py
  - [ ] Token length validation
  - [ ] Injection pattern detection
  - [ ] Rate limiting hooks
  
- [ ] Implement output_guard.py
  - [ ] Hallucination detection
  - [ ] Confidence scoring for pricing
  - [ ] Markdown safety checks
  - [ ] S3 URL validation

### Phase 6: Specialist Agents
- [ ] Implement RAG Agent
  - [ ] Call MCP query_dji_manual_vector_db
  - [ ] Process results and S3 URLs
  
- [ ] Implement Diagnostic Agent
  - [ ] Error code extraction from queries
  - [ ] Call MCP lookup_dji_error_code_db
  - [ ] Format resolution steps
  
- [ ] Implement Pricing Agent
  - [ ] HTTP calls to agent-system-b
  - [ ] Confidence scoring
  - [ ] Format pricing responses

### Phase 7: Summarizer Agent
- [ ] Implement response synthesis
- [ ] Format diagnostic section (Markdown table)
- [ ] Format RAG section with S3 image links
- [ ] Format pricing section
- [ ] Extract and deduplicate sources

### Phase 8: LangSmith Tracing Integration
- [ ] Configure LangSmith in config.py
- [ ] Wire tracing to Supervisor Agent
- [ ] Wire tracing to specialist agents
- [ ] Tag runs with metadata (intent, drone_model, user_id)
- [ ] Configure feedback hooks for manual review

### Phase 9: API Endpoints & Streaming
- [ ] Implement POST /api/v1/chat
  - [ ] Full pipeline execution
  - [ ] SSE streaming response
  - [ ] Error handling
  
- [ ] Implement POST /api/v1/admin/ingest
  - [ ] PDF validation
  - [ ] Authentication (if needed)
  - [ ] Progress tracking

- [ ] Implement POST /api/v1/chat for agent-system-b
- [ ] Implement WebSocket for whisper-stt-service

### Phase 10: Testing & Evaluation
- [ ] Latency benchmarking (target: p95 <1500ms)
- [ ] Intent classification accuracy (target: >90%)
- [ ] Vector search recall/precision
- [ ] Hallucination rate (target: <5%)
- [ ] End-to-end integration tests

---

## 🚀 Deployment Checklist

### Docker Build & Push
- [ ] Build agent-system-a image
- [ ] Build agent-system-b image
- [ ] Build mcp-server image
- [ ] Build whisper-stt-service image
- [ ] Test docker-compose up locally

### Local Testing
- [ ] All containers start successfully
- [ ] Health check endpoints respond (200 OK)
- [ ] Service-to-service connectivity verified
- [ ] Qdrant ready and accessible
- [ ] S3 write test successful

### Integration Testing
- [ ] End-to-end /api/v1/chat flow
- [ ] Error handling and fallbacks
- [ ] SSE streaming works
- [ ] MCP tools respond correctly
- [ ] Agent-system-b A2A calls work

### Production Deployment
- [ ] Environment variables configured
- [ ] AWS IAM policies set
- [ ] S3 bucket ready
- [ ] LangSmith tracing configured
- [ ] Monitoring & logging set up

---

## 📊 Evaluation & Metrics

### Ground Truth Dataset
- [ ] Populate ground_truth_qa.json with 50+ test cases
- [ ] Label expected intents for each query
- [ ] Label relevant manual pages
- [ ] Label expected error codes
- [ ] Add pricing test cases

### Error Code Database
- [ ] Expand error_codes.json with 100+ codes
- [ ] Add resolution steps for each code
- [ ] Include related codes
- [ ] Document severity levels

### Baseline Metrics (MVP Target)
- [ ] p95 latency: <1500ms
- [ ] Intent classification F1: >0.90
- [ ] Vector search recall@5: >0.85
- [ ] Hallucination rate: <5%
- [ ] Source attribution: >95% accurate

---

## 📚 Documentation

- [x] context.md - Complete system architecture (MASTER DOCUMENT)
- [x] README.md - Quick start guide
- [x] EVALUATION.md - Evaluation framework
- [x] PROJECT_STRUCTURE.md - Directory layout
- [ ] API_REFERENCE.md - OpenAPI/Swagger docs
- [ ] DEVELOPMENT.md - Local development setup
- [ ] DEPLOYMENT.md - Production deployment guide

---

## 🎯 Current Status

**Initialization Phase: COMPLETE ✅**

All scaffolding, boilerplate, and configuration files have been created. The project structure matches the specification exactly. All 5 containers are properly organized with:
- Complete Docker setup
- FastAPI entry points
- Source code organization with proper imports
- Configuration management
- Pipeline stages defined
- Specialist agents defined
- HTTP clients for inter-service communication
- MCP tool definitions
- Evaluation scripts

**Ready for: Implementation Phase**

The codebase is now ready for actual implementation of:
1. LangGraph state machines
2. Vector database operations
3. MCP tool execution
4. BERT model training
5. Agent orchestration logic
6. End-to-end pipeline integration

---

## 📖 Quick Reference

### Start Development
```bash
# Set up environment
cp .env.example .env
# Edit .env with your credentials

# Start services
docker-compose up --build

# Run tests
python scripts/run_evaluation.py --mode full
```

### Key Files to Edit Next
1. `services/agent-system-a/src/pipeline/supervisor.py` - LangGraph setup
2. `services/mcp-server/tools/qdrant_rag_tool.py` - Vector search
3. `services/mcp-server/tools/ingest_tool.py` - PDF ingestion
4. `scripts/train_bert_classifier.py` - Model training

### Context Reference
- Architecture details: See `context.md` sections 1-4
- Tool definitions: See `context.md` section 6
- Evaluation metrics: See `EVALUATION.md`
- Project structure: See `PROJECT_STRUCTURE.md`
