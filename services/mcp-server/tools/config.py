"""
Shared configuration constants for MCP server tools.

Single source of truth — import from here instead of redefining in each file.
"""

import os

# Qdrant
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "dji_manuals_parent_child")

# Embedding
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536

# Parent-child chunk sizes
PARENT_CHUNK_SIZE = 1500
PARENT_CHUNK_OVERLAP = 200
CHILD_CHUNK_SIZE = 300
CHILD_CHUNK_OVERLAP = 50
