"""
Configuration management for agent-system-a
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Base configuration"""
    
    # OpenAI
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4")
    
    # LangSmith
    LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY")
    LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT", "dji-rag-system")
    
    # AWS
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
    AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
    S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "dji-multimodal-rag-assets")
    
    # Service URLs
    QDRANT_URL = os.getenv("QDRANT_URL", "http://vector-db:6333")
    MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://mcp-server:8002")
    AGENT_B_URL = os.getenv("AGENT_B_URL", "http://agent-system-b:8001")
    WHISPER_URL = os.getenv("WHISPER_URL", "http://whisper-stt-service:9000")

    # MongoDB Atlas
    MONGODB_URI = os.getenv("MONGODB_URI")
    MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "dji_rag")
    
    # Agent Limits
    MAX_ITERATIONS = 5
    MAX_INPUT_TOKENS = 8192
    MIN_INTENT_CONFIDENCE = 0.7
    
    # Timeouts
    MCP_TOOL_TIMEOUT = 30
    VENDOR_CALL_TIMEOUT = 10
    VECTOR_SEARCH_TIMEOUT = 5


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    LOG_LEVEL = "DEBUG"


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    LOG_LEVEL = "INFO"


def get_config():
    """Get configuration based on environment"""
    env = os.getenv("ENVIRONMENT", "development")
    if env == "production":
        return ProductionConfig()
    return DevelopmentConfig()
