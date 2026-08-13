"""
whisper-stt-service: Speech-to-Text Microservice

WebSocket endpoint for real-time audio transcription
Powered by faster-whisper (CTranslate2)
Forwards transcripts to agent-system-a
"""

from fastapi import FastAPI, WebSocket
import logging
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Whisper STT Service",
    description="Speech-to-text transcription microservice",
    version="1.0.0"
)

# Configuration
AGENT_A_URL = os.getenv("AGENT_A_URL", "http://agent-system-a:8000")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "whisper-stt-service",
        "version": "1.0.0"
    }


@app.websocket("/ws/transcribe")
async def websocket_transcribe(websocket: WebSocket):
    """
    WebSocket endpoint for real-time transcription
    
    Connection flow:
    1. Client connects and sends audio chunks
    2. Service transcribes in real-time
    3. Returns transcript
    4. Forwards to agent-system-a /api/v1/chat
    """
    await websocket.accept()
    logger.info("WebSocket connection accepted")
    
    try:
        # TODO: Implement WebSocket transcription pipeline
        # 1. Receive audio chunks
        # 2. Buffer and transcribe with faster-whisper
        # 3. Send back transcript in real-time
        # 4. Forward to agent-system-a
        
        while True:
            data = await websocket.receive_bytes()
            
            # TODO: Transcribe audio chunk
            transcript = "Transcription pending implementation"
            
            await websocket.send_json({
                "status": "transcribing",
                "transcript": transcript
            })
    
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
        await websocket.close(code=1000)


@app.post("/api/v1/transcribe")
async def transcribe_file(request: dict):
    """
    HTTP endpoint for file-based transcription
    
    Request:
        - audio_file (bytes): Audio file (WAV, MP3, etc.)
        - language (str, optional): Language code
    
    Returns:
        dict: Transcribed text
    """
    try:
        # TODO: Implement file transcription
        logger.info("File transcription request")
        
        return {
            "status": "pending",
            "transcript": ""
        }
    
    except Exception as e:
        logger.error(f"Transcription error: {str(e)}")
        return {
            "status": "error",
            "error": str(e)
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9000)
