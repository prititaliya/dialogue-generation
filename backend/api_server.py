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
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

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

def update_transcript_incremental(meeting_name: str, speaker: str, text: str, is_final: bool = False, broadcast: bool = True) -> Path:
    """
    Incrementally update transcript JSON file for each word/speech event.
    - For interim events: Update the last entry if same speaker, or create new entry
    - For final events: Mark current entry as final
    """
    # Try to import fcntl for file locking (Unix systems only)
    try:
        import fcntl
        HAS_FCNTL = True
    except ImportError:
        HAS_FCNTL = False  # Windows doesn't have fcntl
    
    file_path = get_transcript_file_path(meeting_name)
    
    try:
        # Load existing data or create new structure
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                # Use file locking to prevent race conditions (Unix only)
                if HAS_FCNTL:
                    try:
                        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                        data = json.load(f)
                    finally:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                else:
                    data = json.load(f)
        else:
            data = {
                "meeting_name": meeting_name,
                "transcripts": [],
                "total_entries": 0
            }
        
        transcripts = data.get("transcripts", [])
        
        if is_final:
            # Final event: Mark the last entry as final if it matches this speaker
            text_stripped = text.strip()
            if not text_stripped:
                # Skip empty text
                return file_path
                
            if transcripts:
                last_entry = transcripts[-1]
                last_text = last_entry.get("text", "").strip()
                
                if last_entry.get("speaker") == speaker and not last_entry.get("is_final", False):
                    # Update existing interim entry to final
                    # Only update if text is different or an extension
                    if last_text != text_stripped:
                        transcripts[-1] = {
                            "speaker": speaker,
                            "text": text_stripped,
                            "is_final": True
                        }
                    # If text is exactly the same, just mark as final (no update needed)
                elif last_entry.get("speaker") == speaker and last_entry.get("is_final", False):
                    # Same speaker, final entry - check if text is an extension or duplicate
                    if last_text == text_stripped:
                        # Exact duplicate - skip adding
                        logger.debug(f"⏭️  Skipping duplicate final transcript: {speaker} - {text_stripped[:30]}...")
                        return file_path
                    elif last_text in text_stripped and len(text_stripped) > len(last_text):
                        # Text is an extension, update it
                        transcripts[-1] = {
                            "speaker": speaker,
                            "text": text_stripped,
                            "is_final": True
                        }
                    else:
                        # Check if this exact text already exists in recent entries (prevent repeats)
                        # Check last 3 entries to catch duplicates
                        is_duplicate = False
                        for entry in transcripts[-3:]:
                            if (entry.get("speaker") == speaker and 
                                entry.get("text", "").strip() == text_stripped and 
                                entry.get("is_final", False)):
                                is_duplicate = True
                                logger.debug(f"⏭️  Skipping duplicate final transcript (found in recent entries): {speaker} - {text_stripped[:30]}...")
                                break
                        
                        if not is_duplicate:
                            # New final entry from same speaker
                            transcripts.append({
                                "speaker": speaker,
                                "text": text_stripped,
                                "is_final": True
                            })
                        else:
                            # Skip duplicate
                            return file_path
                else:
                    # Different speaker - check if this exact text already exists in recent entries
                    is_duplicate = False
                    for entry in transcripts[-3:]:
                        if (entry.get("speaker") == speaker and 
                            entry.get("text", "").strip() == text_stripped and 
                            entry.get("is_final", False)):
                            is_duplicate = True
                            logger.debug(f"⏭️  Skipping duplicate final transcript (different speaker, found in recent entries): {speaker} - {text_stripped[:30]}...")
                            break
                    
                    if not is_duplicate:
                        # Different speaker or no matching entry, create new final entry
                        transcripts.append({
                            "speaker": speaker,
                            "text": text_stripped,
                            "is_final": True
                        })
                    else:
                        # Skip duplicate
                        return file_path
            else:
                # No existing transcripts, create first final entry
                transcripts.append({
                    "speaker": speaker,
                    "text": text_stripped,
                    "is_final": True
                })
        else:
            # Interim event: Update last entry if same speaker, or create new interim entry
            if transcripts:
                last_entry = transcripts[-1]
                if last_entry.get("speaker") == speaker and not last_entry.get("is_final", False):
                    # Update existing interim entry
                    transcripts[-1] = {
                        "speaker": speaker,
                        "text": text.strip(),
                        "is_final": False
                    }
                elif last_entry.get("speaker") == speaker and last_entry.get("is_final", False):
                    # Same speaker but last entry was final, create new interim entry
                    transcripts.append({
                        "speaker": speaker,
                        "text": text.strip(),
                        "is_final": False
                    })
                else:
                    # Different speaker, create new interim entry
                    transcripts.append({
                        "speaker": speaker,
                        "text": text.strip(),
                        "is_final": False
                    })
            else:
                # No existing transcripts, create first interim entry
                transcripts.append({
                    "speaker": speaker,
                    "text": text.strip(),
                    "is_final": False
                })
        
        # Update data structure
        data["transcripts"] = transcripts
        data["total_entries"] = len([t for t in transcripts if t.get("is_final", False)])
        
        # Save back to file with locking (if available)
        with open(file_path, 'w', encoding='utf-8') as f:
            if HAS_FCNTL:
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                    json.dump(data, f, indent=2, ensure_ascii=False)
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            else:
                json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.debug(f"💾 Incrementally updated transcript: {speaker} - {text[:30]}... (final={is_final})")
        
        # Broadcast the update to all connected WebSocket clients
        if broadcast:
            try:
                # Try to get the current event loop
                try:
                    loop = asyncio.get_running_loop()
                    # If we're in an async context, schedule the broadcast as a task
                    asyncio.create_task(
                        transcript_manager.broadcast_transcript(speaker, text.strip(), is_final, meeting_name)
                    )
                except RuntimeError:
                    # No running event loop - this shouldn't happen in async context
                    # But if it does, we'll try to create a new event loop
                    # Note: This is a fallback and may not work in all cases
                    logger.warning(f"⚠️  No running event loop for broadcast, skipping WebSocket update")
            except Exception as e:
                logger.warning(f"⚠️  Error broadcasting transcript update: {e}")
        
        return file_path
        
    except Exception as e:
        logger.error(f"❌ Failed to incrementally update transcript to {file_path}: {e}")
        raise

# File watcher for transcript files
class TranscriptFileWatcher(FileSystemEventHandler):
    """Watch for changes to transcript JSON files and notify watching clients"""
    
    def __init__(self, transcript_manager: 'TranscriptManager'):
        self.transcript_manager = transcript_manager
        self.last_known_state: Dict[str, Dict] = {}  # meeting_name -> last known transcript data
        self.watched_files: Dict[str, Set[WebSocket]] = {}  # meeting_name -> set of watching WebSockets
        self.event_loop: Optional[asyncio.AbstractEventLoop] = None
        
    def add_watcher(self, meeting_name: str, websocket: WebSocket):
        """Add a WebSocket to watch a specific meeting's transcript file"""
        if meeting_name not in self.watched_files:
            self.watched_files[meeting_name] = set()
        self.watched_files[meeting_name].add(websocket)
        logger.info(f"👁️  Added watcher for '{meeting_name}' (total watchers: {len(self.watched_files[meeting_name])})")
        
        # Load initial state
        file_path = get_transcript_file_path(meeting_name)
        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.last_known_state[meeting_name] = data
            except Exception as e:
                logger.error(f"Error loading initial state for {meeting_name}: {e}")
    
    def remove_watcher(self, meeting_name: str, websocket: WebSocket):
        """Remove a WebSocket from watching a meeting's transcript file"""
        if meeting_name in self.watched_files:
            self.watched_files[meeting_name].discard(websocket)
            if len(self.watched_files[meeting_name]) == 0:
                del self.watched_files[meeting_name]
                if meeting_name in self.last_known_state:
                    del self.last_known_state[meeting_name]
            logger.info(f"👁️  Removed watcher for '{meeting_name}'")
    
    def remove_all_watchers_for_websocket(self, websocket: WebSocket):
        """Remove a WebSocket from all watched files"""
        meetings_to_remove = []
        for meeting_name, watchers in list(self.watched_files.items()):
            if websocket in watchers:
                watchers.discard(websocket)
                if len(watchers) == 0:
                    meetings_to_remove.append(meeting_name)
        
        for meeting_name in meetings_to_remove:
            del self.watched_files[meeting_name]
            if meeting_name in self.last_known_state:
                del self.last_known_state[meeting_name]
    
    def on_modified(self, event):
        """Called when a file is modified"""
        if event.is_directory:
            return
        
        file_path = Path(event.src_path)
        if file_path.suffix != '.json':
            return
        
        # Extract meeting name from filename
        meeting_name = file_path.stem
        
        # Only process if someone is watching this file
        if meeting_name not in self.watched_files:
            return
        
        # Small delay to ensure file write is complete
        import time
        time.sleep(0.1)
        
        try:
            # Read the updated file
            with open(file_path, 'r', encoding='utf-8') as f:
                new_data = json.load(f)
            
            # Get last known state
            last_state = self.last_known_state.get(meeting_name, {"transcripts": [], "total_entries": 0})
            last_transcripts = last_state.get("transcripts", [])
            new_transcripts = new_data.get("transcripts", [])
            
            # Find new entries (entries that weren't in the last state)
            last_count = len(last_transcripts)
            new_count = len(new_transcripts)
            
            if new_count > last_count:
                # New entries added - send them to watching clients
                new_entries = new_transcripts[last_count:]
                logger.info(f"📝 Detected {len(new_entries)} new transcript entries in '{meeting_name}'")
                
                # Update last known state
                self.last_known_state[meeting_name] = new_data
                
                # Send new entries to all watching WebSockets
                self._send_updates_to_watchers(meeting_name, new_entries)
            elif new_count == last_count and new_transcripts != last_transcripts:
                # Same count but content changed (likely an update to last entry)
                # Check if the last entry was updated
                if new_transcripts and last_transcripts:
                    last_new = new_transcripts[-1]
                    last_old = last_transcripts[-1]
                    if last_new != last_old:
                        # Last entry was updated
                        logger.info(f"📝 Detected update to last transcript entry in '{meeting_name}'")
                        self.last_known_state[meeting_name] = new_data
                        self._send_updates_to_watchers(meeting_name, [last_new], is_update=True)
        
        except Exception as e:
            logger.error(f"Error processing file change for {meeting_name}: {e}")
    
    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        """Set the event loop to use for sending updates from file watcher thread"""
        self.event_loop = loop
    
    def _send_updates_to_watchers(self, meeting_name: str, new_entries: List[Dict], is_update: bool = False):
        """Send new/updated transcript entries to all watching WebSockets"""
        if meeting_name not in self.watched_files:
            return
        
        watchers = list(self.watched_files[meeting_name])
        if not watchers:
            return
        
        message = {
            "type": "transcript_update" if is_update else "transcript_new",
            "meeting_name": meeting_name,
            "transcripts": new_entries,
            "is_update": is_update
        }
        
        # Schedule the async send operation on the event loop
        # This is called from a file watcher thread, so we need to use run_coroutine_threadsafe
        if self.event_loop is None:
            # Try to get the event loop
            try:
                self.event_loop = asyncio.get_running_loop()
            except RuntimeError:
                try:
                    self.event_loop = asyncio.get_event_loop()
                except RuntimeError:
                    logger.error("No event loop available for sending file updates")
                    return
        
        # Use run_coroutine_threadsafe to schedule from another thread
        asyncio.run_coroutine_threadsafe(
            self._async_send_updates(watchers, message, meeting_name),
            self.event_loop
        )
    
    async def _async_send_updates(self, watchers: List[WebSocket], message: Dict, meeting_name: str):
        """Async helper to send updates to watchers"""
        disconnected = set()
        for websocket in watchers:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Error sending file update to client: {e}")
                disconnected.add(websocket)
        
        # Remove disconnected clients
        for ws in disconnected:
            self.remove_watcher(meeting_name, ws)
            self.transcript_manager.disconnect(ws)

# Global transcript manager
class TranscriptManager:
    def __init__(self):
        self.connections: Set[WebSocket] = set()
        self.transcripts: List[Tuple[str, str, bool]] = []  # (speaker, text, is_final)
        self.speaker_label_map: Dict[str, str] = {}
        self.lock = asyncio.Lock()
        self.file_watcher = TranscriptFileWatcher(self)
        self.observer: Optional[Observer] = None
    
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
        # Remove from all file watchers
        self.file_watcher.remove_all_watchers_for_websocket(websocket)
        logger.info(f"Client disconnected. Total connections: {len(self.connections)}")
    
    def start_file_observer(self):
        """Start the file system observer to watch transcript files"""
        if self.observer is None:
            self.observer = Observer()
            self.observer.schedule(self.file_watcher, str(TRANSCRIPTS_DIR), recursive=False)
            self.observer.start()
            logger.info(f"👁️  Started file observer for transcript directory: {TRANSCRIPTS_DIR}")
    
    def stop_file_observer(self):
        """Stop the file system observer"""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None
            logger.info("👁️  Stopped file observer")
    
    async def broadcast_transcript(self, speaker: str, text: str, is_final: bool = True, meeting_name: Optional[str] = None):
        """Broadcast a transcript to all connected clients"""
        async with self.lock:
            text_stripped = text.strip()
            if not text_stripped:
                # Skip empty text
                return
                
            # Store transcript
            is_duplicate = False
            if is_final:
                # Check if this is an update to the last transcript from the same speaker
                updated_existing = False
                
                if self.transcripts:
                    last_speaker, last_text, last_is_final = self.transcripts[-1]
                    if speaker == last_speaker:
                        if not last_is_final:
                            # Converting interim to final - update existing entry
                            self.transcripts[-1] = (speaker, text_stripped, is_final)
                            updated_existing = True
                        elif last_text == text_stripped:
                            # Exact duplicate - skip adding
                            logger.debug(f"⏭️  Skipping duplicate broadcast transcript: {speaker} - {text_stripped[:30]}...")
                            is_duplicate = True
                        elif last_text in text_stripped and len(text_stripped) > len(last_text):
                            # Both final, text is extension - update existing entry
                            self.transcripts[-1] = (speaker, text_stripped, is_final)
                            updated_existing = True
                        else:
                            # Check if this exact text already exists in recent entries (prevent repeats)
                            for entry in self.transcripts[-3:]:
                                entry_speaker, entry_text, entry_is_final = entry
                                if (entry_speaker == speaker and 
                                    entry_text == text_stripped and 
                                    entry_is_final):
                                    is_duplicate = True
                                    logger.debug(f"⏭️  Skipping duplicate broadcast transcript (found in recent entries): {speaker} - {text_stripped[:30]}...")
                                    break
                    else:
                        # Different speaker - check if this exact text already exists in recent entries
                        for entry in self.transcripts[-3:]:
                            entry_speaker, entry_text, entry_is_final = entry
                            if (entry_speaker == speaker and 
                                entry_text == text_stripped and 
                                entry_is_final):
                                is_duplicate = True
                                logger.debug(f"⏭️  Skipping duplicate broadcast transcript (different speaker, found in recent entries): {speaker} - {text_stripped[:30]}...")
                                break
                
                if not updated_existing and not is_duplicate:
                    self.transcripts.append((speaker, text_stripped, is_final))
            else:
                # For interim transcripts, update last entry if same speaker, or append new
                updated_existing = False
                if self.transcripts:
                    last_speaker, last_text, last_is_final = self.transcripts[-1]
                    if speaker == last_speaker and not last_is_final:
                        # Update existing interim entry
                        self.transcripts[-1] = (speaker, text_stripped, is_final)
                        updated_existing = True
                
                if not updated_existing:
                    self.transcripts.append((speaker, text_stripped, is_final))
        
        # Broadcast to all connected clients (only if not a duplicate)
        if is_final and is_duplicate:
            # Don't broadcast duplicates
            return
            
        message = {
            "type": "transcript",
            "speaker": speaker,
            "text": text_stripped,
            "is_final": is_final,
            "meeting_name": meeting_name
        }
        
        logger.info(f"Broadcasting transcript: {speaker} - {text_stripped[:50]}... (final={is_final}, connections={len(self.connections)})")
        
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
    
    async def update_transcripts(self, speaker: str, text: str, is_final: bool = True):
        """Update internal transcript list without broadcasting (for accumulation)"""
        async with self.lock:
            text_stripped = text.strip()
            if not text_stripped:
                # Skip empty text
                return
                
            # Check if this is an update to the last transcript from the same speaker
            updated_existing = False
            is_duplicate = False
            
            if self.transcripts:
                last_speaker, last_text, last_is_final = self.transcripts[-1]
                if speaker == last_speaker:
                    if not is_final and not last_is_final:
                        # Both interim - update existing entry
                        self.transcripts[-1] = (speaker, text_stripped, is_final)
                        updated_existing = True
                    elif is_final and not last_is_final:
                        # Converting interim to final - update existing entry
                        self.transcripts[-1] = (speaker, text_stripped, is_final)
                        updated_existing = True
                    elif is_final and last_is_final:
                        # Both final - check for duplicates or extensions
                        if last_text == text_stripped:
                            # Exact duplicate - skip adding
                            logger.debug(f"⏭️  Skipping duplicate transcript in manager: {speaker} - {text_stripped[:30]}...")
                            is_duplicate = True
                        elif last_text in text_stripped and len(text_stripped) > len(last_text):
                            # Text is extension - update existing entry
                            self.transcripts[-1] = (speaker, text_stripped, is_final)
                            updated_existing = True
                        else:
                            # Check if this exact text already exists in recent entries (prevent repeats)
                            for entry in self.transcripts[-3:]:
                                entry_speaker, entry_text, entry_is_final = entry
                                if (entry_speaker == speaker and 
                                    entry_text == text_stripped and 
                                    entry_is_final):
                                    is_duplicate = True
                                    logger.debug(f"⏭️  Skipping duplicate transcript in manager (found in recent entries): {speaker} - {text_stripped[:30]}...")
                                    break
                else:
                    # Different speaker - check if this exact text already exists in recent entries
                    for entry in self.transcripts[-3:]:
                        entry_speaker, entry_text, entry_is_final = entry
                        if (entry_speaker == speaker and 
                            entry_text == text_stripped and 
                            entry_is_final):
                            is_duplicate = True
                            logger.debug(f"⏭️  Skipping duplicate transcript in manager (different speaker, found in recent entries): {speaker} - {text_stripped[:30]}...")
                            break
            
            if not updated_existing and not is_duplicate:
                self.transcripts.append((speaker, text_stripped, is_final))
    
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
    # Set the event loop for the file watcher
    transcript_manager.file_watcher.set_event_loop(asyncio.get_running_loop())
    # Start file observer for transcript files
    transcript_manager.start_file_observer()
    yield
    # Stop file observer on shutdown
    transcript_manager.stop_file_observer()
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
                    message_type = message.get("type")
                    
                    if message_type == "request_transcript":
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
                    
                    elif message_type == "watch_transcript":
                        # Client wants to watch a transcript file for real-time updates
                        meeting_name = message.get("meeting_name") or message.get("room_name")
                        if meeting_name:
                            logger.info(f"👁️  Client {client_host} wants to watch transcript: {meeting_name}")
                            transcript_manager.file_watcher.add_watcher(meeting_name, websocket)
                            
                            # Also send current transcript if file exists
                            transcript_data = load_transcript_from_file(meeting_name)
                            if transcript_data:
                                message_to_send = {
                                    "type": "complete_transcript",
                                    "meeting_title": transcript_data.get("meeting_name", meeting_name),
                                    "transcripts": transcript_data.get("transcripts", [])
                                }
                                try:
                                    await websocket.send_json(message_to_send)
                                    logger.info(f"✅ Sent initial transcript to watcher: {meeting_name}")
                                except Exception as e:
                                    logger.error(f"Error sending initial transcript: {e}")
                        else:
                            logger.warning(f"⚠️  watch_transcript message missing meeting_name")
                    
                    elif message_type == "unwatch_transcript":
                        # Client wants to stop watching a transcript file
                        meeting_name = message.get("meeting_name") or message.get("room_name")
                        if meeting_name:
                            logger.info(f"👁️  Client {client_host} wants to stop watching transcript: {meeting_name}")
                            transcript_manager.file_watcher.remove_watcher(meeting_name, websocket)
                        else:
                            logger.warning(f"⚠️  unwatch_transcript message missing meeting_name")
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

