"""
FastMCP Server — Isolated MCP Tool Executor

Exposes domain tools over HTTP on port 8002:
1. query_dji_manual_vector_db — Parent-child hybrid retrieval + Redis cache + reranking
2. lookup_dji_error_code_db   — Error code exact-match lookup
3. ingest_and_index_pdf       — Admin: PDF extraction + S3 + chunking + Qdrant indexing

Also runs a FastAPI HTTP wrapper for REST calls from agent-system-a.
"""

import os
import base64
import logging
from typing import Annotated, Optional

from dotenv import load_dotenv
from fastmcp import FastMCP
from fastapi import FastAPI
from pydantic import Field

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# FastMCP App
# ─────────────────────────────────────────────────────────────────────────────

mcp = FastMCP(
    name="DJI MCP Server",
    instructions=(
        "You are the tool execution layer for a DJI drone RAG system. "
        "You provide hybrid vector search over manuals (parent-child with reranking), "
        "error code lookups, and PDF ingestion capabilities."
    ),
)


# ── Tool 1: Vector Search (Parent-Child + Reranker + Cache) ──────────────────

@mcp.tool()
def query_dji_manual_vector_db(
    query: Annotated[str, Field(description="Natural language search query")],
    drone_model: Annotated[Optional[str], Field(description="Filter by drone model, e.g. 'DJI Mini 4 Pro'")] = None,
    top_k: Annotated[int, Field(description="Number of parent chunks to return")] = 4,
    topic_filter: Annotated[Optional[str], Field(description="Filter by topic, e.g. 'battery'")] = None,
    modality_filter: Annotated[Optional[str], Field(description="Filter by modality, e.g. 'text', 'image'")] = None,
) -> list:
    """
    Hybrid parent-child retrieval over DJI manual embeddings.

    Pipeline: embed → cache check → dense + BM25 → parent dedup → rerank → top-k.
    Returns parent chunks (1500 chars) with metadata and image paths.
    """
    from tools.qdrant_rag_tool import query_dji_manual_vector_db as _search
    return _search(query=query, drone_model=drone_model, top_k=top_k,
                   topic_filter=topic_filter, modality_filter=modality_filter)


# ── Tool 2: Error Code Lookup ────────────────────────────────────────────────

@mcp.tool()
def lookup_dji_error_code_db(
    error_code: Annotated[str, Field(description="DJI error code, e.g. 'E001' or 'COMPASS_ERR'")],
) -> dict:
    """
    Look up a DJI error code and return resolution steps, severity, and related codes.
    Performs case-insensitive exact matching against the error code database.
    """
    from tools.error_code_tool import lookup_dji_error_code_db as _lookup
    return _lookup(error_code=error_code)


# ── Tool 3: PDF Ingestion (Admin) ────────────────────────────────────────────

@mcp.tool()
def ingest_and_index_pdf(
    file_bytes_b64: Annotated[str, Field(description="Base64-encoded PDF file bytes")],
    filename: Annotated[str, Field(description="Original PDF filename")],
    drone_model: Annotated[str, Field(description="Target drone model for metadata tagging")],
) -> dict:
    """
    Admin tool: Extract PDF (text + images with GPT-4o captions to S3),
    then ingest with parent-child chunking strategy into Qdrant.
    """
    from tools.extraction import extract_pdf_pages
    from tools.ingestion import ingest_pages

    pdf_bytes = base64.b64decode(file_bytes_b64)

    # Step 1: Extract text + images (with S3 upload + GPT-4o captions)
    pages = extract_pdf_pages(pdf_bytes, filename, drone_model)

    # Step 2: Parent-child chunking + embed + index to Qdrant
    result = ingest_pages(pages, drone_model, filename)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI HTTP Wrapper (REST interface for agent-system-a)
# ─────────────────────────────────────────────────────────────────────────────

http_app = FastAPI(
    title="DJI MCP Server (HTTP)",
    description="HTTP wrapper around FastMCP tools for direct REST calls",
    version="2.0.0",
)


@http_app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "mcp-server",
        "version": "2.0.0",
        "tools": [
            "query_dji_manual_vector_db",
            "lookup_dji_error_code_db",
            "ingest_and_index_pdf",
        ],
    }


@http_app.get("/api/v1/tools")
async def list_tools():
    """List available MCP tools."""
    return {
        "tools": [
            {
                "name": "query_dji_manual_vector_db",
                "description": "Parent-child hybrid retrieval with reranking and Redis cache",
            },
            {
                "name": "lookup_dji_error_code_db",
                "description": "DJI error code lookup with resolution steps",
            },
            {
                "name": "ingest_and_index_pdf",
                "description": "Admin: PDF extraction (GPT-4o captions + S3) + parent-child ingestion to Qdrant",
            },
        ]
    }


@http_app.post("/api/v1/call_tool")
async def call_tool(request: dict):
    """
    Execute an MCP tool via HTTP.

    Request: {"tool_name": str, "arguments": dict}
    Response: {"status": "success", "output": ...} or {"status": "error", "error": str}
    """
    from tools.qdrant_rag_tool import query_dji_manual_vector_db as _search
    from tools.error_code_tool import lookup_dji_error_code_db as _lookup
    from tools.documents_tool import list_documents as _list_docs, delete_document as _delete_doc

    tool_name = request.get("tool_name")
    arguments = request.get("arguments", {})

    logger.info(f"HTTP call_tool: {tool_name}")

    try:
        if tool_name == "query_dji_manual_vector_db":
            output = _search(**arguments)

        elif tool_name == "lookup_dji_error_code_db":
            output = _lookup(**arguments)

        elif tool_name == "ingest_and_index_pdf":
            from tools.extraction import extract_pdf_pages
            from tools.ingestion import ingest_pages

            if "file_bytes_b64" in arguments:
                pdf_bytes = base64.b64decode(arguments["file_bytes_b64"])
                filename = arguments.get("filename", "upload.pdf")
                drone_model = arguments.get("drone_model", "unknown")

                pages = extract_pdf_pages(pdf_bytes, filename, drone_model)
                output = ingest_pages(pages, drone_model, filename)
            else:
                output = {"error": "file_bytes_b64 is required"}

        elif tool_name == "list_documents":
            output = _list_docs()

        elif tool_name == "delete_document":
            source_name = arguments.get("source_name")
            if not source_name:
                return {"status": "error", "error": "source_name is required"}
            output = _delete_doc(source_name)

        else:
            return {"status": "error", "error": f"Unknown tool: {tool_name}"}

        return {"status": "success", "output": output}

    except Exception as e:
        logger.error(f"Tool execution error: {e}")
        return {"status": "error", "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(http_app, host="0.0.0.0", port=8002)
