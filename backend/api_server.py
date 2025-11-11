"""
FastAPI server for transcript streaming via WebSocket
"""
import os
import asyncio
import json
import logging
from typing import Set, Dict, List, Tuple, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(".env.local")

logger = logging.getLogger("api_server")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Directory to store transcript JSON files (in backend directory)
BACKEND_DIR = Path(__file__).parent.absolute()
TRANSCRIPTS_DIR = BACKEND_DIR / "transcripts"
TRANSCRIPTS_DIR.mkdir(exist_ok=True)
logger.info(f"📁 Transcripts directory: {TRANSCRIPTS_DIR}")

def get_transcript_file_path(meeting_name: str) -> Path:
    """Get the file path for a meeting's transcript"""
    # Sanitize meeting name to be filesystem-safe
    safe_name = "".join(c for c in meeting_name if c.isalnum() or c in ('-', '_', ' ')).strip()
    safe_name = safe_name.replace(' ', '_')
    return TRANSCRIPTS_DIR / f"{safe_name}.json"

def save_transcript_to_file(meeting_name: str, transcripts: List[Tuple[str, str]]) -> Path:
    """Save transcripts to a JSON file"""
    file_path = get_transcript_file_path(meeting_name)
    transcript_data = {
        "meeting_name": meeting_name,
        "transcripts": [
            {"speaker": speaker, "text": text, "is_final": True}
            for speaker, text in transcripts
        ],
        "total_entries": len(transcripts)
    }
    
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(transcript_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"💾 Saved transcript to {file_path.absolute()} ({len(transcripts)} entries)")
        logger.info(f"📂 Full path: {file_path.resolve()}")
        return file_path
    except Exception as e:
        logger.error(f"❌ Failed to save transcript to {file_path}: {e}")
        raise

def load_transcript_from_file(meeting_name: str) -> Optional[Dict]:
    """Load transcript from a JSON file"""
    file_path = get_transcript_file_path(meeting_name)
    
    if not file_path.exists():
        logger.warning(f"📄 Transcript file not found: {file_path}")
        return None
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logger.info(f"📖 Loaded transcript from {file_path} ({data.get('total_entries', 0)} entries)")
        return data
    except Exception as e:
        logger.error(f"❌ Error loading transcript from {file_path}: {e}")
        return None

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
    
    async def update_transcripts(self, speaker: str, text: str):
        """Update internal transcript list without broadcasting (for accumulation)"""
        async with self.lock:
            # Check if this is an update to the last transcript from the same speaker
            updated_existing = False
            if self.transcripts:
                last_speaker, last_text, _ = self.transcripts[-1]
                if speaker == last_speaker and last_text in text:
                    self.transcripts[-1] = (speaker, text, True)
                    updated_existing = True
            
            if not updated_existing:
                self.transcripts.append((speaker, text, True))
    
    async def send_complete_transcript(self, meeting_title: str, transcript_list: List[Tuple[str, str]] = None):
        """Send complete transcript to all connected clients when recording stops"""
        async with self.lock:
            # Use provided transcript_list or fall back to internal transcripts
            if transcript_list is None:
                transcript_list = [(sp, txt) for sp, txt, _ in self.transcripts]
            
            # Save transcript to file
            if transcript_list:
                save_transcript_to_file(meeting_title, transcript_list)
            
            # Convert transcript list to the format expected by frontend
            transcript_data = [
                {"speaker": speaker, "text": text, "is_final": True}
                for speaker, text in transcript_list
            ]
            
            message = {
                "type": "complete_transcript",
                "meeting_title": meeting_title,
                "transcripts": transcript_data
            }
            
            logger.info(f"Sending complete transcript: {meeting_title} with {len(transcript_data)} entries (connections={len(self.connections)})")
            
            if len(self.connections) == 0:
                logger.warning("No WebSocket connections available to send complete transcript to!")
            
            disconnected = set()
            for connection in self.connections:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"Error sending complete transcript to client: {e}")
                    disconnected.add(connection)
            
            # Remove disconnected clients
            for conn in disconnected:
                self.disconnect(conn)

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
async def get_transcripts(meeting_name: Optional[str] = Query(None, description="Meeting name to retrieve transcript for")):
    """Get transcripts - either from file (if meeting_name provided) or from memory"""
    if meeting_name:
        # Load from file
        transcript_data = load_transcript_from_file(meeting_name)
        if transcript_data:
            return transcript_data
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Transcript not found for meeting: {meeting_name}"
            )
    else:
        # Return from memory (backward compatibility)
        return {
            "transcripts": [
                {"speaker": sp, "text": txt, "is_final": is_final}
                for sp, txt, is_final in transcript_manager.transcripts
            ],
            "speaker_labels": transcript_manager.speaker_label_map
        }

@app.get("/transcripts/list")
async def list_all_transcripts():
    """List all available transcripts from the transcripts directory"""
    try:
        transcript_files = []
        if TRANSCRIPTS_DIR.exists():
            for file_path in TRANSCRIPTS_DIR.glob("*.json"):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        # Extract meeting name from filename (remove .json extension)
                        meeting_name = file_path.stem
                        transcript_files.append({
                            "meeting_name": data.get("meeting_name", meeting_name),
                            "file_name": meeting_name,
                            "total_entries": data.get("total_entries", 0),
                            "last_modified": file_path.stat().st_mtime
                        })
                except Exception as e:
                    logger.warning(f"Error reading transcript file {file_path}: {e}")
                    continue
        
        # Sort by last modified (newest first)
        transcript_files.sort(key=lambda x: x.get("last_modified", 0), reverse=True)
        
        logger.info(f"📋 Listed {len(transcript_files)} transcript files")
        return {
            "transcripts": transcript_files,
            "count": len(transcript_files)
        }
    except Exception as e:
        logger.error(f"Error listing transcripts: {e}")
        raise HTTPException(status_code=500, detail=f"Error listing transcripts: {str(e)}")

class TranscriptUpdateRequest(BaseModel):
    transcripts: List[Tuple[str, str]]
    room_name: str

@app.post("/transcripts/update")
async def update_transcripts_from_main(request: TranscriptUpdateRequest):
    """Update transcripts from main.py process and save to file"""
    logger.info(f"Received transcript update from main.py: {len(request.transcripts)} transcripts for room {request.room_name}")
    # Clear existing and set new transcripts
    async with transcript_manager.lock:
        transcript_manager.transcripts = [
            (speaker, text, True) for speaker, text in request.transcripts
        ]
    
    # Save to file
    if request.transcripts:
        save_transcript_to_file(request.room_name, request.transcripts)
    
    logger.info(f"Updated transcript manager with {len(transcript_manager.transcripts)} transcripts")
    return {"status": "ok", "count": len(transcript_manager.transcripts), "meeting_name": request.room_name}

class TokenRequest(BaseModel):
    room_name: str
    identity: Optional[str] = None

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
                detail="LiveKit API credentials not configured. Please create a .env.local file in the backend directory with LIVEKIT_API_KEY and LIVEKIT_API_SECRET. See README.md for setup instructions."
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
        # Keep connection alive and handle incoming messages
        while True:
            try:
                data = await websocket.receive_text()
                try:
                    message = json.loads(data)
                    logger.info(f"📨 Received WebSocket message from {client_host}: {message}")
                    if message.get("type") == "request_transcript":
                        # Client is requesting the complete transcript
                        room_name = message.get("room_name", "Meeting")
                        logger.info(f"🎯 Client {client_host} requested transcript for room: {room_name}")
                        
                        # Try to load from file first
                        transcript_data = load_transcript_from_file(room_name)
                        if transcript_data:
                            # Send from file
                            logger.info(f"📖 Loaded transcript from file: {room_name}.json ({transcript_data.get('total_entries', 0)} entries)")
                            message_to_send = {
                                "type": "complete_transcript",
                                "meeting_title": transcript_data.get("meeting_name", room_name),
                                "transcripts": transcript_data.get("transcripts", [])
                            }
                            
                            disconnected = set()
                            for connection in transcript_manager.connections:
                                try:
                                    await connection.send_json(message_to_send)
                                except Exception as e:
                                    logger.error(f"Error sending transcript to client: {e}")
                                    disconnected.add(connection)
                            
                            for conn in disconnected:
                                transcript_manager.disconnect(conn)
                            logger.info(f"✅ Sent transcript from file to {client_host}")
                        else:
                            # Fall back to memory
                            logger.info(f"📊 Current transcripts in manager: {len(transcript_manager.transcripts)}")
                            if transcript_manager.transcripts:
                                logger.info(f"📝 Sending {len(transcript_manager.transcripts)} transcripts from memory to {client_host}")
                            else:
                                logger.warning(f"⚠️  No transcripts available in API server or file. Transcripts may be in main.py process.")
                            await transcript_manager.send_complete_transcript(room_name)
                            logger.info(f"✅ Sent complete transcript response to {client_host}")
                except json.JSONDecodeError:
                    # Not a JSON message, ignore
                    logger.warning(f"Received non-JSON message: {data}")
                    pass
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

