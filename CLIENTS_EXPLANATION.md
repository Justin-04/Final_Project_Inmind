# Clients Explanation - agent-system-a Communication

## Overview

`agent-system-a` (the main orchestrator) needs to communicate with **two other services** to perform its tasks. It uses HTTP clients to communicate with them.

```
agent-system-a (Port 8000)
├── MCPClient              → talks to mcp-server (Port 5000)
└── SystemBClient          → talks to agent-system-b (Port 8001)
```

---

## 1. MCPClient (`mcp_client.py`)

### What It Does
Calls the **MCP server** to execute tools (like vector search, error lookup, PDF ingestion).

### Usage Example
```python
from src.clients.mcp_client import MCPClient

# Create client
mcp = MCPClient(mcp_url="http://mcp-server:5000")

# Call a tool
results = mcp.call_tool(
    tool_name="query_dji_manual_vector_db",
    arguments={
        "query": "compass calibration",
        "drone_model": "mini_4_pro",
        "top_k": 5
    }
)

# Get list of available tools
tools = mcp.list_tools()

# Check if service is healthy
is_healthy = mcp.health_check()
```

### Where It's Used
**In the Specialist Agents:**

```python
# RAG Agent uses it
class RAGAgent:
    def __init__(self, mcp_client):
        self.mcp_client = mcp_client
    
    def execute(self, query: str, drone_model: str):
        # Calls MCP tool: query_dji_manual_vector_db
        results = self.mcp_client.call_tool(
            tool_name="query_dji_manual_vector_db",
            arguments={"query": query, "drone_model": drone_model}
        )
        return results

# Diagnostic Agent uses it
class DiagnosticAgent:
    def __init__(self, mcp_client):
        self.mcp_client = mcp_client
    
    def execute(self, error_code: str):
        # Calls MCP tool: lookup_dji_error_code_db
        result = self.mcp_client.call_tool(
            tool_name="lookup_dji_error_code_db",
            arguments={"error_code": error_code}
        )
        return result
```

### Methods Available

| Method | Purpose | Example |
|--------|---------|---------|
| `call_tool()` | Execute an MCP tool | `mcp.call_tool("query_dji_manual_vector_db", {...})` |
| `list_tools()` | Get available tools | `tools = mcp.list_tools()` |
| `health_check()` | Check service status | `is_ok = mcp.health_check()` |

---

## 2. SystemBClient (`system_b_client.py`)

### What It Does
Calls the **vendor/pricing service** (agent-system-b) to search for vendors and get pricing information.

### Usage Example
```python
from src.clients.system_b_client import SystemBClient

# Create client
system_b = SystemBClient(agent_b_url="http://agent-system-b:8001")

# Search for vendors
vendors = system_b.search_vendors(
    drone_model="mini_4_pro",
    part_category="battery",
    search_query="DJI Mini 4 Pro Battery"
)

# Get pricing for a part
pricing = system_b.get_pricing(part_id="DJI-MINI-4-BATTERY-001")

# Check if service is healthy
is_healthy = system_b.health_check()
```

### Where It's Used
**In the Pricing Agent:**

```python
# Pricing Agent uses it
class PricingAgent:
    def __init__(self, system_b_client):
        self.system_b_client = system_b_client
    
    def execute(self, drone_model: str, part_category: str):
        # Calls agent-system-b
        vendors = self.system_b_client.search_vendors(
            drone_model=drone_model,
            part_category=part_category
        )
        return vendors
```

### Methods Available

| Method | Purpose | Example |
|--------|---------|---------|
| `search_vendors()` | Find vendors by model/category | `system_b.search_vendors("mini_4_pro", "battery")` |
| `get_pricing()` | Get price for a part | `system_b.get_pricing("part-id-123")` |
| `health_check()` | Check service status | `is_ok = system_b.health_check()` |

---

## Data Flow: How They're Used Together

### User Query for Pricing
```
User: "Where can I buy a battery for DJI Mini 4 Pro?"
         ↓
[agent-system-a receives query]
         ↓
[Intent Classifier] → Intent: "PRICING"
         ↓
[Supervisor routes to Pricing Agent]
         ↓
[Pricing Agent]
  └─ Uses SystemBClient
     ├─ search_vendors("mini_4_pro", "battery")
     └─ Returns: [vendor1, vendor2, vendor3]
         ↓
[Summarizer synthesizes response]
         ↓
[Response to User] → "Here are vendors and prices for batteries..."
```

### User Query for Technical Info
```
User: "What are common compass errors for Mini 4 Pro?"
         ↓
[agent-system-a receives query]
         ↓
[Intent Classifier] → Intent: "DIAGNOSTIC"
         ↓
[Supervisor routes to Diagnostic + RAG Agents (parallel)]
         ↓
[RAG Agent]               [Diagnostic Agent]
├─ Uses MCPClient        └─ Uses MCPClient
│  └─ query_dji_manual   └─ lookup_dji_error_code_db
│     _vector_db            ("COMPASS_ERR")
└─ Returns: manual       └─ Returns: resolution
           excerpts                   steps
         ↓
[Summarizer synthesizes both responses]
         ↓
[Response to User] → "Here are the compass errors and how to fix them..."
```

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                  agent-system-a (Port 8000)                 │
│                   Main Orchestrator (FastAPI)               │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │           src/clients/                              │  │
│  │  ┌────────────────┐    ┌────────────────────────┐  │  │
│  │  │  MCPClient     │    │  SystemBClient         │  │  │
│  │  │                │    │                        │  │  │
│  │  │ • call_tool()  │    │ • search_vendors()     │  │  │
│  │  │ • list_tools() │    │ • get_pricing()        │  │  │
│  │  │ • health_check()    │ • health_check()       │  │  │
│  │  └────────────────┘    └────────────────────────┘  │  │
│  └─────────────────────────────────────────────────────┘  │
│           │                          │                    │
└───────────┼──────────────────────────┼────────────────────┘
            │                          │
     HTTP POST/GET            HTTP POST/GET
            │                          │
            ▼                          ▼
    ┌────────────────┐        ┌────────────────┐
    │  mcp-server    │        │ agent-system-b │
    │  (Port 5000)   │        │  (Port 8001)   │
    │                │        │                │
    │ Tools:         │        │ Services:      │
    │ • query_dji..  │        │ • vendor_search│
    │ • lookup_err.. │        │ • get_pricing  │
    │ • ingest_pdf.. │        │                │
    └────────────────┘        └────────────────┘
            │
            ▼
    ┌────────────────┐
    │ vector-db      │
    │ (Qdrant)       │
    │ (Port 6333)    │
    └────────────────┘
```

---

## How to Initialize These Clients in Your Code

### In main.py (agent-system-a)

```python
from src.clients.mcp_client import MCPClient
from src.clients.system_b_client import SystemBClient
from src.agents.rag_agent import RAGAgent
from src.agents.diagnostic import DiagnosticAgent
from src.agents.summarizer import SummarizerAgent

# Create clients
mcp_client = MCPClient(
    mcp_url=os.getenv("MCP_SERVER_URL", "http://mcp-server:5000")
)

system_b_client = SystemBClient(
    agent_b_url=os.getenv("AGENT_B_URL", "http://agent-system-b:8001")
)

# Initialize agents with clients
rag_agent = RAGAgent(mcp_client)
diagnostic_agent = DiagnosticAgent(mcp_client)
pricing_agent = PricingAgent(system_b_client)  # Not yet implemented
summarizer_agent = SummarizerAgent()

# Use in your endpoints
@app.post("/api/v1/chat")
async def chat(request: dict):
    query = request.get("query")
    
    # Route to appropriate agent
    if intent == "rag":
        result = rag_agent.execute(query, drone_model)
    elif intent == "diagnostic":
        result = diagnostic_agent.execute(query)
    # ... etc
```

---

## Summary

| Client | Talks To | Purpose | Used By |
|--------|----------|---------|---------|
| **MCPClient** | mcp-server:5000 | Execute MCP tools (search, lookup, ingest) | RAG Agent, Diagnostic Agent |
| **SystemBClient** | agent-system-b:8001 | Search vendors, get pricing | Pricing Agent |

Both use **HTTP** to communicate (no direct Python imports) to maintain **service isolation** and allow independent scaling/deployment.
