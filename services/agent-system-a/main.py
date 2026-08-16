"""
agent-system-a: Primary LangGraph Orchestrator

Multi-agent system for DJI drone support.
- SSE streaming responses
- MongoDB conversation persistence (last 4 messages as context)
- Calls MCP server for RAG & diagnostics
- Calls agent-system-b for pricing over HTTP A2A
"""

import os
import sys
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
from sse_starlette.sse import EventSourceResponse
from dotenv import load_dotenv
import httpx

load_dotenv()

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from graph.workflow import build_graph
from db.conversation_store import ConversationStore
from auth.routes import router as auth_router, set_users_collection
from auth.middleware import get_current_user, require_admin

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# App Lifecycle
# ─────────────────────────────────────────────────────────────────────────────

conversation_store: Optional[ConversationStore] = None
agent_graph = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global conversation_store, agent_graph

    # Startup
    mongodb_uri = os.getenv("MONGODB_URI")
    if mongodb_uri:
        conversation_store = ConversationStore(mongodb_uri)
        # Set up auth users collection
        set_users_collection(conversation_store.db["users"])
        logger.info("MongoDB connected ✓")
    else:
        logger.warning("MONGODB_URI not set — conversation history disabled")

    agent_graph = build_graph()
    logger.info("LangGraph compiled ✓")

    yield

    # Shutdown
    if conversation_store:
        conversation_store.client.close()


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI App
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="DJI RAG Agent System A",
    description="LangGraph multi-agent orchestrator for DJI drone support",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include auth routes
app.include_router(auth_router)


# ─────────────────────────────────────────────────────────────────────────────
# Request/Response Models
# ─────────────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    query: str = Field(..., description="User's question")
    user_id: str = Field(default="anonymous", description="User identifier")
    conversation_id: Optional[str] = Field(default=None, description="Existing conversation to continue")


class ChatResponse(BaseModel):
    conversation_id: str
    response: str
    intent: str
    metadata: dict = {}


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

def _get_tools_executed(result: dict) -> list:
    """Extract which tools were executed based on the pipeline result."""
    tools = []
    route = result.get("route", "")

    if route == "rag_agent":
        rag_result = result.get("rag_result") or {}
        tools.append({
            "tool_name": "query_dji_manual_vector_db",
            "target": "mcp-server",
            "status": "success" if rag_result.get("chunks") else "no_results",
            "chunks_returned": len(rag_result.get("chunks", [])),
        })
    elif route == "diagnostic_agent":
        diag_result = result.get("diagnostic_result") or {}
        if diag_result.get("error_codes"):
            tools.append({
                "tool_name": "lookup_dji_error_code_db",
                "target": "mcp-server",
                "status": "success",
                "codes_found": len(diag_result.get("error_codes", [])),
            })
        if diag_result.get("rag_chunks"):
            tools.append({
                "tool_name": "query_dji_manual_vector_db",
                "target": "mcp-server",
                "status": "success",
                "chunks_returned": len(diag_result.get("rag_chunks", [])),
            })
    elif route == "pricing_agent":
        pricing_result = result.get("pricing_result") or {}
        tools.append({
            "tool_name": "vendor_pricing_search",
            "target": "agent-system-b",
            "status": "success" if pricing_result.get("vendors") else "no_results",
            "vendors_returned": len(pricing_result.get("vendors", [])),
            "multi_model": pricing_result.get("multi_model", False),
        })

    return tools


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "agent-system-a",
        "version": "1.0.0",
        "graph_loaded": agent_graph is not None,
        "mongodb_connected": conversation_store is not None,
    }


@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, user: dict = Depends(get_current_user)):
    """
    Main chat endpoint. Runs the full LangGraph pipeline.

    - Loads last 4 messages from MongoDB for context
    - Runs: input_guard → classifier → supervisor → specialist → summarizer
    - Saves user + assistant messages to MongoDB
    - Returns the final response
    """
    if not agent_graph:
        raise HTTPException(status_code=503, detail="Agent graph not initialized")

    try:
        # Get or create conversation
        conversation_id = request.conversation_id
        conversation_history = []

        if conversation_store:
            conversation_id = await conversation_store.get_or_create_conversation(
                conversation_id, request.user_id
            )
            # Load last 4 messages for context
            conversation_history = await conversation_store.get_recent_messages(
                conversation_id, limit=4
            )
            # Save user message
            await conversation_store.add_message(conversation_id, "user", request.query)
        else:
            conversation_id = conversation_id or "no-db"

        print(f"\n{'='*60}")
        print(f"  💬 CHAT REQUEST")
        print(f"  User: {request.user_id}")
        print(f"  Conv: {conversation_id}")
        print(f"  Query: {request.query}")
        print(f"  History: {len(conversation_history)} messages")
        print(f"{'='*60}")

        # Run the LangGraph pipeline
        result = agent_graph.invoke({
            "query": request.query,
            "user_id": request.user_id,
            "conversation_id": conversation_id,
            "conversation_history": conversation_history,
            "intent": "",
            "confidence": 0.0,
            "input_safe": True,
            "guardrail_message": None,
            "iteration_count": 0,
            "max_iterations": 5,
            "route": "",
            "rag_result": None,
            "diagnostic_result": None,
            "pricing_result": None,
            "final_response": "",
        })

        final_response = result.get("final_response", "No response generated.")

        # Save assistant response to MongoDB
        if conversation_store:
            await conversation_store.add_message(conversation_id, "assistant", final_response)

        print(f"\n{'='*60}")
        print(f"  ✅ RESPONSE SENT ({len(final_response)} chars)")
        print(f"{'='*60}\n")

        return ChatResponse(
            conversation_id=conversation_id,
            response=final_response,
            intent=result.get("intent", "unknown"),
            metadata={
                "confidence": result.get("confidence", 0.0),
                "route": result.get("route", ""),
                "iteration_count": result.get("iteration_count", 0),
                "guardrail": {
                    "passed": result.get("input_safe", True),
                    "flagged_reason": result.get("guardrail_message"),
                },
                "bert_classification": {
                    "intent": result.get("intent", "unknown"),
                    "confidence": result.get("confidence", 0.0),
                },
                "route_taken": ["input_guard", "bert_classifier", "supervisor", result.get("route", ""), "summarizer"],
                "tools_executed": _get_tools_executed(result),
            },
        )

    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An error occurred processing your request.")


@app.post("/api/v1/chat/stream")
async def chat_stream(request: ChatRequest, user: dict = Depends(get_current_user)):
    """
    SSE streaming chat endpoint.
    Streams the final response token-by-token (simulated from full response).
    """
    if not agent_graph:
        raise HTTPException(status_code=503, detail="Agent graph not initialized")

    async def event_generator():
        try:
            # Get or create conversation
            conversation_id = request.conversation_id
            conversation_history = []

            if conversation_store:
                conversation_id = await conversation_store.get_or_create_conversation(
                    conversation_id, request.user_id
                )
                conversation_history = await conversation_store.get_recent_messages(
                    conversation_id, limit=4
                )
                await conversation_store.add_message(conversation_id, "user", request.query)
            else:
                conversation_id = conversation_id or "no-db"

            # Send conversation_id immediately
            yield {"event": "metadata", "data": json.dumps({"conversation_id": conversation_id})}

            # Run pipeline
            yield {"event": "status", "data": json.dumps({"step": "processing"})}

            result = agent_graph.invoke({
                "query": request.query,
                "user_id": request.user_id,
                "conversation_id": conversation_id,
                "conversation_history": conversation_history,
                "intent": "",
                "confidence": 0.0,
                "input_safe": True,
                "guardrail_message": None,
                "iteration_count": 0,
                "max_iterations": 5,
                "route": "",
                "rag_result": None,
                "diagnostic_result": None,
                "pricing_result": None,
                "final_response": "",
            })

            final_response = result.get("final_response", "No response generated.")

            # Stream response in chunks
            chunk_size = 20  # characters per chunk
            for i in range(0, len(final_response), chunk_size):
                chunk = final_response[i:i + chunk_size]
                yield {"event": "token", "data": json.dumps({"content": chunk})}

            # Save to MongoDB
            if conversation_store:
                await conversation_store.add_message(conversation_id, "assistant", final_response)

            # Done
            yield {"event": "done", "data": json.dumps({
                "conversation_id": conversation_id,
                "intent": result.get("intent", ""),
                "full_response": final_response,
            })}

        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield {"event": "error", "data": json.dumps({"error": str(e)})}

    return EventSourceResponse(event_generator())


# ─────────────────────────────────────────────────────────────────────────────
# Admin Endpoints (require admin role)
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/v1/admin/ingest")
async def admin_ingest(request: dict, user: dict = Depends(require_admin)):
    """Admin: Ingest a PDF into the vector database."""
    MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8002")

    pdf_file = request.get("pdf_file")
    drone_model = request.get("drone_model")
    source_name = request.get("source_name")

    if not all([pdf_file, drone_model, source_name]):
        raise HTTPException(status_code=400, detail="pdf_file, drone_model, and source_name are required")

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{MCP_SERVER_URL}/api/v1/call_tool",
                json={
                    "tool_name": "ingest_and_index_pdf",
                    "arguments": {
                        "file_bytes_b64": pdf_file,
                        "filename": source_name,
                        "drone_model": drone_model,
                    },
                },
            )
            data = resp.json()

        if data.get("status") == "success":
            output = data["output"]
            return {
                "status": output.get("status", "success"),
                "filename": output.get("filename", source_name),
                "pages": output.get("pages", 0),
                "chunks": output.get("chunks", 0),
            }
        else:
            raise HTTPException(status_code=500, detail=data.get("error", "Ingestion failed"))

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/admin/documents")
async def admin_list_documents(user: dict = Depends(require_admin)):
    """Admin: List all ingested documents."""
    MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8002")

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{MCP_SERVER_URL}/api/v1/call_tool",
                json={"tool_name": "list_documents", "arguments": {}},
            )
            data = resp.json()

        if data.get("status") == "success":
            # Transform to match frontend's KnowledgeDocument interface:
            # {source: str, drone_model: str, chunk_count: int}
            raw_docs = data["output"]
            documents = []
            for doc in raw_docs:
                documents.append({
                    "source": doc.get("filename", doc.get("source", "unknown")),
                    "drone_model": doc.get("drone_model", "unknown"),
                    "chunk_count": doc.get("chunks", doc.get("chunk_count", 0)),
                })
            return {"documents": documents}
        else:
            return {"documents": [], "error": data.get("error")}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/admin/documents/{source_name}")
async def admin_delete_document(source_name: str, user: dict = Depends(require_admin)):
    """Admin: Delete all vectors for a document source."""
    MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8002")

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{MCP_SERVER_URL}/api/v1/call_tool",
                json={
                    "tool_name": "delete_document",
                    "arguments": {"source_name": source_name},
                },
            )
            data = resp.json()

        if data.get("status") == "success":
            output = data["output"]
            is_deleted = output.get("status") == "deleted"
            return {
                "deleted": is_deleted,
                "source": source_name,
                "message": f"Removed {output.get('chunks_removed', 0)} chunks" if is_deleted else output.get("message", "Not found"),
            }
        else:
            return {"deleted": False, "source": source_name, "message": data.get("error", "Delete failed")}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Conversation History Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/v1/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    """Get full conversation history."""
    if not conversation_store:
        raise HTTPException(status_code=503, detail="MongoDB not configured")
    doc = await conversation_store.get_conversation(conversation_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return doc


@app.get("/api/v1/conversations")
async def list_conversations(user_id: str = "anonymous", limit: int = 20):
    """List user's conversations."""
    if not conversation_store:
        raise HTTPException(status_code=503, detail="MongoDB not configured")
    conversations = await conversation_store.list_conversations(user_id, limit)
    return {"conversations": conversations}


@app.delete("/api/v1/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """Delete a conversation."""
    if not conversation_store:
        raise HTTPException(status_code=503, detail="MongoDB not configured")
    deleted = await conversation_store.delete_conversation(conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "deleted"}


@app.put("/api/v1/conversations/{conversation_id}/rename")
async def rename_conversation(conversation_id: str, request: dict):
    """Rename a conversation."""
    if not conversation_store:
        raise HTTPException(status_code=503, detail="MongoDB not configured")
    title = request.get("title", "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")
    updated = await conversation_store.rename_conversation(conversation_id, title)
    if not updated:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "renamed", "title": title}


# ─────────────────────────────────────────────────────────────────────────────
# Voice Input (Whisper STT)
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/v1/voice")
async def voice_chat(audio: UploadFile = File(...), user_id: str = "anonymous", conversation_id: str = None, user: dict = Depends(get_current_user)):
    """
    Voice input endpoint. Accepts audio file, transcribes with OpenAI Whisper,
    then runs the transcription through the chat pipeline.
    """
    from openai import OpenAI

    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        audio_bytes = await audio.read()
        
        import io
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = audio.filename or "audio.webm"

        print(f"\n🎤 [Voice] Transcribing {len(audio_bytes)} bytes...")

        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language="en",
        )

        transcribed_text = transcript.text.strip()
        print(f"🎤 [Voice] Transcribed: '{transcribed_text}'")

        if not transcribed_text:
            raise HTTPException(status_code=400, detail="Could not transcribe audio")

        # Run through chat pipeline
        chat_request = ChatRequest(
            query=transcribed_text,
            user_id=user_id,
            conversation_id=conversation_id,
        )
        result = await chat(chat_request)

        return {
            "transcription": transcribed_text,
            "conversation_id": result.conversation_id,
            "response": result.response,
            "intent": result.intent,
            "metadata": result.metadata,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Voice error: {e}")
        raise HTTPException(status_code=500, detail="Voice processing failed")


@app.post("/api/v1/voice/transcribe")
async def voice_transcribe_only(audio: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """
    Transcribe-only endpoint. Returns the text without running chat pipeline.
    Used for "record → show in input → user reviews → send" flow.
    """
    from openai import OpenAI

    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        audio_bytes = await audio.read()

        import io
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = audio.filename or "audio.webm"

        print(f"\n🎤 [Transcribe] {len(audio_bytes)} bytes...")

        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language="en",
        )

        transcribed_text = transcript.text.strip()
        print(f"🎤 [Transcribe] Result: '{transcribed_text}'")

        return {"transcription": transcribed_text}

    except Exception as e:
        logger.error(f"Transcribe error: {e}")
        raise HTTPException(status_code=500, detail="Transcription failed")


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
