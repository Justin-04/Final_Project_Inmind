# Multi-Agent DJI Drone RAG System

Enterprise-grade distributed RAG system for DJI drone maintenance, diagnostics, specifications, and purchasing.

## Quick Start

See `context.md` for complete system architecture and specifications.

## Project Structure

- `context.md` - Master project specification and architecture
- `docker-compose.yml` - Multi-container orchestration
- `services/` - Isolated microservices (5 containers)
- `data/` - Domain datasets and reference materials
- `models/` - ML artifacts and fine-tuned models
- `scripts/` - Automation and evaluation scripts
- `frontend/` - React/Next.js web UI

## Development Setup

```bash
# Copy environment template
cp .env.example .env

# Update .env with your credentials
# Then start services
docker-compose up --build
```

## Services

1. **agent-system-a** (Port 8000) - LangGraph orchestrator
2. **agent-system-b** (Port 8001) - Vendor/pricing microservice
3. **mcp-server** (Port 5000) - MCP tool executor
4. **whisper-stt-service** (Port 9000) - Speech-to-text
5. **vector-db** (Port 6333) - Qdrant vector database

## Documentation

- `context.md` - Full system context and architecture
- `EVALUATION.md` - Metrics and evaluation framework
