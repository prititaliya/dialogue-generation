"""
FastAPI server for transcript streaming via WebSocket
"""
import os
import asyncio
import json
import logging
from typing import Set, Dict, List, Tuple
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv(".env.local")

logger = logging.getLogger("api_server")

# Global transcript manager
class TranscriptManager:
    def __init__(self):
        self.connections: Set[WebSocket] = set()
        self.transcripts: List[Tuple[str, str, bool]] = []  # (speaker, text, is_final)
        self.speaker_label_map: Dict[str, str] = {}
        self.lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.connections.add(websocket)
        logger.info(f"Client connected. Total connections: {len(self.connections)}")
        
        # Send existing transcripts to new client
        if self.transcripts:
            await websocket.send_json({
                "type": "initial_transcripts",
                "transcripts": [
                    {"speaker": sp, "text": txt, "is_final": is_final}
                    for sp, txt, is_final in self.transcripts
                ]
            })
    
    def disconnect(self, websocket: WebSocket):
        self.connections.discard(websocket)
        logger.info(f"Client disconnected. Total connections: {len(self.connections)}")
    
    async def broadcast_transcript(self, speaker: str, text: str, is_final: bool = True):
        """Broadcast a transcript to all connected clients"""
        async with self.lock:
            # Store transcript
            if is_final:
                # Check if this is an update to the last transcript from the same speaker
                updated_existing = False
                if self.transcripts:
                    last_speaker, last_text, _ = self.transcripts[-1]
                    if speaker == last_speaker and last_text in text:
                        self.transcripts[-1] = (speaker, text, is_final)
                        updated_existing = True
                
                if not updated_existing:
                    self.transcripts.append((speaker, text, is_final))
            else:
                # For interim transcripts, we can append temporarily or just broadcast
                pass
        
        # Broadcast to all connected clients
        message = {
            "type": "transcript",
            "speaker": speaker,
            "text": text,
            "is_final": is_final
        }
        
        logger.info(f"Broadcasting transcript: {speaker} - {text[:50]}... (final={is_final}, connections={len(self.connections)})")
        
        if len(self.connections) == 0:
            logger.warning("No WebSocket connections available to send transcript to!")
        
        disconnected = set()
        for connection in self.connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error sending message to client: {e}")
                disconnected.add(connection)
        
        # Remove disconnected clients
        for conn in disconnected:
            self.disconnect(conn)
    
    def update_speaker_label(self, speaker_id: str, speaker_name: str):
        """Update speaker label mapping"""
        self.speaker_label_map[speaker_id] = speaker_name
    
    def get_speaker_label(self, speaker_id: str) -> str:
        """Get speaker label for a speaker ID"""
        return self.speaker_label_map.get(speaker_id, f"Speaker {speaker_id}")

# Global transcript manager instance
transcript_manager = TranscriptManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("API server starting up...")
    yield
    logger.info("API server shutting down...")

app = FastAPI(lifespan=lifespan)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Transcript API Server", "status": "running"}

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "websocket_endpoint": "/ws/transcripts",
        "active_connections": len(transcript_manager.connections),
        "total_transcripts": len(transcript_manager.transcripts)
    }

@app.get("/transcripts")
async def get_transcripts():
    """Get all stored transcripts"""
    return {
        "transcripts": [
            {"speaker": sp, "text": txt, "is_final": is_final}
            for sp, txt, is_final in transcript_manager.transcripts
        ],
        "speaker_labels": transcript_manager.speaker_label_map
    }

class TokenRequest(BaseModel):
    room_name: str
    identity: str = None

@app.post("/token")
async def generate_token(request: TokenRequest):
    """Generate a LiveKit access token for a room"""
    try:
        from livekit import api
        
        api_key = os.getenv("LIVEKIT_API_KEY")
        api_secret = os.getenv("LIVEKIT_API_SECRET")
        
        if not api_key or not api_secret:
            raise HTTPException(
                status_code=500,
                detail="LiveKit API credentials not configured"
            )
        
        identity = request.identity
        if not identity:
            import uuid
            identity = f"user-{uuid.uuid4().hex[:8]}"
        
        token = api.AccessToken(api_key, api_secret) \
            .with_identity(identity) \
            .with_name(identity) \
            .with_grants(api.VideoGrants(
                room_join=True,
                room=request.room_name,
                can_publish=True,
                can_subscribe=True,
            ))
        
        return {
            "token": token.to_jwt(),
            "url": os.getenv("LIVEKIT_URL", "ws://localhost:7880"),
            "room_name": request.room_name,
            "identity": identity
        }
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="LiveKit API package not installed. Install with: pip install livekit-api"
        )
    except Exception as e:
        logger.error(f"Error generating token: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/ws/transcripts")
async def websocket_endpoint(websocket: WebSocket):
    client_host = websocket.client.host if websocket.client else "unknown"
    
    try:
        await transcript_manager.connect(websocket)
        logger.info(f"WebSocket client connected from {client_host}. Total connections: {len(transcript_manager.connections)}")
    except Exception as e:
        logger.error(f"Failed to accept WebSocket connection from {client_host}: {e}")
        try:
            await websocket.close(code=1000, reason="Server error")
        except:
            pass
        return
    
    try:
        # Keep connection alive
        while True:
            try:
                await websocket.receive_text()
            except WebSocketDisconnect:
                break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error for client {client_host}: {e}")
    finally:
        transcript_manager.disconnect(websocket)
        logger.info(f"WebSocket client {client_host} disconnected. Total connections: {len(transcript_manager.connections)}")

def get_transcript_manager() -> TranscriptManager:
    """Get the global transcript manager instance"""
    return transcript_manager

