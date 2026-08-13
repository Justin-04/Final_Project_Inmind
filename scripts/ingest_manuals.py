"""
Script: Ingest DJI Manual PDFs

Ingests PDF manuals from data/manuals/ directory
Triggers MCP tool: ingest_and_index_pdf
Indexes chunks and images into Qdrant + S3
"""

import os
import sys
import logging
import httpx
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:5000")
MANUALS_DIR = Path(__file__).parent.parent / "data" / "manuals"


def ingest_manual(pdf_path: str, drone_model: str, source_name: str):
    """
    Ingest a single PDF manual
    
    Args:
        pdf_path: Path to PDF file
        drone_model: Target drone model
        source_name: Human-readable source name
    """
    try:
        logger.info(f"Ingesting: {source_name} ({pdf_path})")
        
        # Read PDF file
        with open(pdf_path, 'rb') as f:
            pdf_bytes = f.read()
        
        # Call MCP ingestion tool
        with httpx.Client() as client:
            response = client.post(
                f"{MCP_SERVER_URL}/api/v1/call_tool",
                json={
                    "tool_name": "ingest_and_index_pdf",
                    "arguments": {
                        "pdf_file": pdf_bytes.hex(),  # Base64 equivalent
                        "drone_model": drone_model,
                        "source_name": source_name
                    }
                }
            )
            
            result = response.json()
            
            if result.get("status") == "success":
                logger.info(f"✓ Ingested: {result.get('indexed_chunks')} chunks, "
                           f"{result.get('extracted_images')} images")
            else:
                logger.error(f"✗ Ingestion failed: {result.get('error')}")
    
    except Exception as e:
        logger.error(f"Error ingesting {pdf_path}: {str(e)}")


def main():
    """Main ingestion script"""
    logger.info(f"Starting manual ingestion from {MANUALS_DIR}")
    
    # TODO: Define drone models and PDFs to ingest
    # Example structure:
    manuals_to_ingest = [
        # ("mini_4_pro", "DJI_Mini_4_Pro_User_Manual.pdf", "Official User Manual"),
        # ("air_3", "DJI_Air_3_User_Manual.pdf", "Official User Manual"),
        # ("mavic_3_pro", "DJI_Mavic_3_Pro_User_Manual.pdf", "Official User Manual"),
    ]
    
    for drone_model, pdf_file, source_name in manuals_to_ingest:
        pdf_path = MANUALS_DIR / pdf_file
        if pdf_path.exists():
            ingest_manual(str(pdf_path), drone_model, source_name)
        else:
            logger.warning(f"PDF not found: {pdf_path}")
    
    logger.info("Ingestion complete")


if __name__ == "__main__":
    main()
