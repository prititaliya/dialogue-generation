"""
FastAPI server for transcript streaming via WebSocket
"""

import os
import asyncio
import json
import logging
from typing import Set, Dict, List, Tuple, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from sqlalchemy.orm import Session
from database.database import get_db, init_db
from auth import (
    authenticate_user,
    create_user,
    create_access_token,
    get_user_by_username,
    get_user_by_email,
    verify_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    timedelta,
)
from room_user_mapping import get_user_id_for_room

load_dotenv(".env.local")

logger = logging.getLogger("api_server")
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Directory to store transcript JSON files (in backend directory)
BACKEND_DIR = Path(__file__).parent.absolute()
TRANSCRIPTS_DIR = BACKEND_DIR / "transcripts"
TRANSCRIPTS_DIR.mkdir(exist_ok=True)
logger.info(f"📁 Transcripts directory: {TRANSCRIPTS_DIR}")


def get_transcript_file_path(meeting_name: str) -> Path:
    """Get the file path for a meeting's transcript"""
    # Sanitize meeting name to be filesystem-safe
    safe_name = "".join(
        c for c in meeting_name if c.isalnum() or c in ("-", "_", " ")
    ).strip()
    safe_name = safe_name.replace(" ", "_")
    return TRANSCRIPTS_DIR / f"{safe_name}.json"


def save_transcript_to_file(
    meeting_name: str, transcripts: List[Tuple[str, str]], delete_after_storage: bool = False
) -> Path:
    """Save transcripts to a JSON file. Optionally store in vector DB and delete JSON file.
    
    Args:
        meeting_name: Name of the meeting
        transcripts: List of (speaker, text) tuples
        delete_after_storage: If True, store to vector DB and delete JSON file. 
                             If False, only save to JSON file (default).
    """
    file_path = get_transcript_file_path(meeting_name)
    
    # Get user_id from room mapping to include in metadata
    from room_user_mapping import get_user_id_for_room
    user_id = get_user_id_for_room(meeting_name)
    
    transcript_data = {
        "meeting_name": meeting_name,
        "transcripts": [
            {"speaker": speaker, "text": text, "is_final": True}
            for speaker, text in transcripts
        ],
        "total_entries": len(transcripts),
    }
    
    # Add user_id to metadata if available
    if user_id:
        transcript_data["user_id"] = user_id

    try:
        # Save to JSON file first (temporary storage for frontend)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(transcript_data, f, indent=2, ensure_ascii=False)

        logger.info(
            f"💾 Saved transcript to {file_path.absolute()} ({len(transcripts)} entries)"
        )
        logger.info(f"📂 Full path: {file_path.resolve()}")
        
        # Only store in vector DB and delete JSON file if explicitly requested
        if not delete_after_storage:
            return file_path
        
        # Now store in vector DB and delete JSON file
        try:
            from room_user_mapping import get_user_id_for_room
            from vector_db.vector_store import store_transcript
            from datetime import datetime
            import uuid
            
            # Get user_id from room mapping
            user_id = get_user_id_for_room(meeting_name)
            
            if user_id is None:
                logger.warning(
                    f"⚠️  No user mapping found for room '{meeting_name}'. "
                    f"Skipping vector DB storage. JSON file will be kept."
                )
                return file_path
            
            # Check if transcript with same meeting_name already exists for this user
            from vector_db.vector_store import get_redis_client
            import json as json_module
            
            client = get_redis_client()
            keys = client.keys("transcript:*")
            existing_meeting_id = None
            
            # Search for existing transcript with same meeting_name and user_id
            for key in keys:
                data = client.hgetall(key)
                stored_meeting_name = data.get(b'meeting_name')
                stored_user_id = data.get(b'user_id')
                
                if stored_meeting_name and stored_user_id:
                    stored_meeting_name_str = stored_meeting_name.decode('utf-8')
                    stored_user_id_str = int(stored_user_id.decode('utf-8'))
                    
                    if stored_meeting_name_str == meeting_name and stored_user_id_str == user_id:
                        # Found existing transcript - extract meeting_id from key
                        existing_meeting_id = key.decode('utf-8').replace('transcript:', '')
                        logger.info(f"📝 Found existing transcript for '{meeting_name}', will update it (meeting_id: {existing_meeting_id})")
                        break
            
            # Generate meeting_id (use existing one if found, otherwise create new)
            timestamp = datetime.now().timestamp()
            if existing_meeting_id:
                meeting_id = existing_meeting_id
                logger.info(f"🔄 Updating existing transcript: {meeting_id}")
            else:
                meeting_id = f"{user_id}_{meeting_name}_{int(timestamp)}"
                logger.info(f"✨ Creating new transcript: {meeting_id}")
            
            # Combine all transcript entries into single text string
            # Format: "Speaker 1: text\nSpeaker 2: text"
            transcript_text_parts = []
            speakers_set = set()
            
            for speaker, text in transcripts:
                if text.strip():  # Only include non-empty text
                    transcript_text_parts.append(f"{speaker}: {text.strip()}")
                    speakers_set.add(speaker)
            
            transcript_text = "\n".join(transcript_text_parts)
            speakers_list = sorted(list(speakers_set))
            
            if not transcript_text:
                logger.warning(
                    f"⚠️  Empty transcript for '{meeting_name}'. Skipping vector DB storage."
                )
                return file_path
            
            # Store in vector DB (will update if meeting_id exists)
            logger.info(f"📊 Storing transcript in vector DB: {meeting_name}")
            stored_meeting_id = store_transcript(
                user_id=user_id,
                meeting_name=meeting_name,
                transcript_text=transcript_text,
                speakers=speakers_list,
                timestamp=timestamp,
                meeting_id=meeting_id,
            )
            
            if stored_meeting_id:
                # Successfully stored in vector DB, delete JSON file
                try:
                    file_path.unlink()
                    logger.info(f"🗑️  Deleted JSON file after successful vector DB storage: {file_path}")
                    logger.info(f"✅ Transcript '{meeting_name}' successfully stored in vector database")
                except Exception as e:
                    logger.warning(f"⚠️  Failed to delete JSON file {file_path}: {e}")
            else:
                logger.error(
                    f"❌ Vector DB storage failed for '{meeting_name}'. "
                    f"JSON file kept as fallback. Check Redis connection!"
                )
                # Don't delete JSON file if vector DB storage failed
                
        except ImportError as e:
            logger.warning(
                f"⚠️  Vector DB modules not available: {e}. "
                f"Keeping JSON file. Install redis and sentence-transformers."
            )
        except Exception as e:
            logger.error(
                f"❌ Error storing transcript in vector DB: {e}. "
                f"Keeping JSON file for fallback."
            )
        
        return file_path
    except Exception as e:
        logger.error(f"❌ Failed to save transcript to {file_path}: {e}")
        raise


def load_transcript_from_file(meeting_name: str, filter_interim: bool = True) -> Optional[Dict]:
    """Load transcript from a JSON file, optionally filtering out interim transcripts and deduplicating"""
    file_path = get_transcript_file_path(meeting_name)

    if not file_path.exists():
        logger.warning(f"📄 Transcript file not found: {file_path}")
        return None

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        transcripts = data.get("transcripts", [])
        
        # Filter out interim transcripts if requested
        if filter_interim:
            # Only keep final transcripts
            final_transcripts = [t for t in transcripts if t.get("is_final", False)]
            
            # Deduplicate: remove exact duplicates (same speaker and text)
            seen = set()
            deduplicated = []
            for entry in final_transcripts:
                speaker = entry.get("speaker", "")
                text = entry.get("text", "").strip()
                key = (speaker, text)
                if key not in seen and text:  # Only add non-empty text
                    seen.add(key)
                    deduplicated.append(entry)
            
            data["transcripts"] = deduplicated
            data["total_entries"] = len(deduplicated)
            
            if len(transcripts) != len(deduplicated):
                logger.info(
                    f"📖 Loaded transcript from {file_path}: filtered {len(transcripts)} -> {len(deduplicated)} final entries (removed {len(transcripts) - len(deduplicated)} interim/duplicates)"
                )
            else:
                logger.info(
                    f"📖 Loaded transcript from {file_path} ({len(deduplicated)} final entries)"
                )
        else:
            logger.info(
                f"📖 Loaded transcript from {file_path} ({len(transcripts)} entries, including interim)"
            )
        
        return data
    except Exception as e:
        logger.error(f"❌ Error loading transcript from {file_path}: {e}")
        return None


def update_transcript_incremental(
    meeting_name: str,
    speaker: str,
    text: str,
    is_final: bool = False,
    broadcast: bool = True,
) -> Path:
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
            with open(file_path, "r", encoding="utf-8") as f:
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
            data = {"meeting_name": meeting_name, "transcripts": [], "total_entries": 0}

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

                if last_entry.get("speaker") == speaker and not last_entry.get(
                    "is_final", False
                ):
                    # Update existing interim entry to final
                    # Only update if text is different or an extension
                    if last_text != text_stripped:
                        transcripts[-1] = {
                            "speaker": speaker,
                            "text": text_stripped,
                            "is_final": True,
                        }
                    # If text is exactly the same, just mark as final (no update needed)
                elif last_entry.get("speaker") == speaker and last_entry.get(
                    "is_final", False
                ):
                    # Same speaker, final entry - check if text is an extension or duplicate
                    if last_text == text_stripped:
                        # Exact duplicate - skip adding
                        logger.debug(
                            f"⏭️  Skipping duplicate final transcript: {speaker} - {text_stripped[:30]}..."
                        )
                        return file_path
                    elif last_text in text_stripped and len(text_stripped) > len(
                        last_text
                    ):
                        # Text is an extension, update it
                        transcripts[-1] = {
                            "speaker": speaker,
                            "text": text_stripped,
                            "is_final": True,
                        }
                    else:
                        # Check if this exact text already exists in recent entries (prevent repeats)
                        # Check last 20 entries to catch duplicates (increased from 3)
                        is_duplicate = False
                        for entry in transcripts[-20:]:
                            if (
                                entry.get("speaker") == speaker
                                and entry.get("text", "").strip() == text_stripped
                                and entry.get("is_final", False)
                            ):
                                is_duplicate = True
                                logger.debug(
                                    f"⏭️  Skipping duplicate final transcript (found in recent entries): {speaker} - {text_stripped[:30]}..."
                                )
                                break

                        if not is_duplicate:
                            # New final entry from same speaker
                            transcripts.append(
                                {
                                    "speaker": speaker,
                                    "text": text_stripped,
                                    "is_final": True,
                                }
                            )
                        else:
                            # Skip duplicate
                            return file_path
                else:
                    # Different speaker - check if this exact text already exists in recent entries
                    # Check last 20 entries to catch duplicates (increased from 3)
                    is_duplicate = False
                    for entry in transcripts[-20:]:
                        if (
                            entry.get("speaker") == speaker
                            and entry.get("text", "").strip() == text_stripped
                            and entry.get("is_final", False)
                        ):
                            is_duplicate = True
                            logger.debug(
                                f"⏭️  Skipping duplicate final transcript (different speaker, found in recent entries): {speaker} - {text_stripped[:30]}..."
                            )
                            break

                    if not is_duplicate:
                        # Different speaker or no matching entry, create new final entry
                        transcripts.append(
                            {
                                "speaker": speaker,
                                "text": text_stripped,
                                "is_final": True,
                            }
                        )
                    else:
                        # Skip duplicate
                        return file_path
            else:
                # No existing transcripts, create first final entry
                transcripts.append(
                    {"speaker": speaker, "text": text_stripped, "is_final": True}
                )
        else:
            # Interim event: Update last entry if same speaker, or create new interim entry
            # IMPORTANT: Interim transcripts should replace previous interim from same speaker
            # to prevent accumulation of duplicate interim updates
            text_stripped = text.strip()
            if not text_stripped:
                # Skip empty text
                return file_path
                
            if transcripts:
                last_entry = transcripts[-1]
                if last_entry.get("speaker") == speaker and not last_entry.get(
                    "is_final", False
                ):
                    # Update existing interim entry (replace, don't accumulate)
                    transcripts[-1] = {
                        "speaker": speaker,
                        "text": text_stripped,
                        "is_final": False,
                    }
                elif last_entry.get("speaker") == speaker and last_entry.get(
                    "is_final", False
                ):
                    # Same speaker but last entry was final, create new interim entry
                    # But first check if this exact interim text already exists (prevent duplicates)
                    is_duplicate = False
                    # Check last 10 entries for duplicate interim transcripts
                    for entry in transcripts[-10:]:
                        if (
                            entry.get("speaker") == speaker
                            and entry.get("text", "").strip() == text_stripped
                            and not entry.get("is_final", False)
                        ):
                            is_duplicate = True
                            logger.debug(
                                f"⏭️  Skipping duplicate interim transcript: {speaker} - {text_stripped[:30]}..."
                            )
                            break
                    
                    if not is_duplicate:
                        transcripts.append(
                            {"speaker": speaker, "text": text_stripped, "is_final": False}
                        )
                else:
                    # Different speaker, create new interim entry
                    # But check for duplicates first
                    is_duplicate = False
                    # Check last 10 entries for duplicate interim transcripts
                    for entry in transcripts[-10:]:
                        if (
                            entry.get("speaker") == speaker
                            and entry.get("text", "").strip() == text_stripped
                            and not entry.get("is_final", False)
                        ):
                            is_duplicate = True
                            logger.debug(
                                f"⏭️  Skipping duplicate interim transcript (different speaker): {speaker} - {text_stripped[:30]}..."
                            )
                            break
                    
                    if not is_duplicate:
                        transcripts.append(
                            {"speaker": speaker, "text": text_stripped, "is_final": False}
                        )
            else:
                # No existing transcripts, create first interim entry
                transcripts.append(
                    {"speaker": speaker, "text": text_stripped, "is_final": False}
                )

        # Update data structure
        data["transcripts"] = transcripts
        data["total_entries"] = len(
            [t for t in transcripts if t.get("is_final", False)]
        )
        
        # Ensure user_id is in metadata (for ownership validation)
        from room_user_mapping import get_user_id_for_room
        user_id = get_user_id_for_room(meeting_name)
        if user_id and "user_id" not in data:
            data["user_id"] = user_id

        # Save back to file with locking (if available)
        with open(file_path, "w", encoding="utf-8") as f:
            if HAS_FCNTL:
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                    json.dump(data, f, indent=2, ensure_ascii=False)
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            else:
                json.dump(data, f, indent=2, ensure_ascii=False)

        logger.debug(
            f"💾 Incrementally updated transcript: {speaker} - {text[:30]}... (final={is_final})"
        )

        # Broadcast the update to all connected WebSocket clients for this user
        if broadcast:
            try:
                # Get user_id from room mapping
                user_id = get_user_id_for_room(meeting_name)
                if user_id is None:
                    logger.warning(
                        f"⚠️  No user_id found for room {meeting_name}, skipping broadcast"
                    )
                else:
                    # Try to get the current event loop
                    try:
                        loop = asyncio.get_running_loop()
                        # If we're in an async context, schedule the broadcast as a task
                        loop.create_task(
                            transcript_manager.broadcast_transcript(
                                speaker, text.strip(), is_final, meeting_name, user_id
                            )
                        )
                    except RuntimeError:
                        # No running event loop - try to get the event loop from the transcript manager
                        # The transcript manager should have access to the API server's event loop
                        try:
                            # Get the event loop that was set for the file watcher
                            if transcript_manager.file_watcher.event_loop:
                                transcript_manager.file_watcher.event_loop.create_task(
                                    transcript_manager.broadcast_transcript(
                                        speaker, text.strip(), is_final, meeting_name, user_id
                                    )
                                )
                            else:
                                # Fallback: use run_coroutine_threadsafe if we have an event loop
                                import threading
                                try:
                                    loop = asyncio.get_event_loop()
                                    if loop.is_running():
                                        asyncio.run_coroutine_threadsafe(
                                            transcript_manager.broadcast_transcript(
                                                speaker, text.strip(), is_final, meeting_name, user_id
                                            ),
                                            loop
                                        )
                                    else:
                                        logger.warning(
                                            "⚠️  No running event loop for broadcast, file watcher will handle updates"
                                        )
                                except Exception:
                                    logger.warning(
                                        "⚠️  No event loop available for broadcast, file watcher will handle updates"
                                    )
                        except Exception as e:
                            logger.warning(
                                f"⚠️  Error scheduling broadcast: {e}. File watcher will handle updates."
                            )
            except Exception as e:
                logger.warning(f"⚠️  Error broadcasting transcript update: {e}")

        return file_path

    except Exception as e:
        logger.error(
            f"❌ Failed to incrementally update transcript to {file_path}: {e}"
        )
        raise


# File watcher for transcript files
class TranscriptFileWatcher(FileSystemEventHandler):
    """Watch for changes to transcript JSON files and notify watching clients"""

    def __init__(self, transcript_manager: "TranscriptManager"):
        self.transcript_manager = transcript_manager
        self.last_known_state: Dict[
            str, Dict
        ] = {}  # meeting_name -> last known transcript data
        self.watched_files: Dict[
            str, Set[WebSocket]
        ] = {}  # meeting_name -> set of watching WebSockets
        self.event_loop: Optional[asyncio.AbstractEventLoop] = None

    def add_watcher(self, meeting_name: str, websocket: WebSocket):
        """Add a WebSocket to watch a specific meeting's transcript file"""
        if meeting_name not in self.watched_files:
            self.watched_files[meeting_name] = set()
        self.watched_files[meeting_name].add(websocket)
        logger.info(
            f"👁️  Added watcher for '{meeting_name}' (total watchers: {len(self.watched_files[meeting_name])})"
        )

        # Load initial state
        file_path = get_transcript_file_path(meeting_name)
        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
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
        """Called when a file is modified - watchdog detects JSON file changes"""
        if event.is_directory:
            return

        file_path = Path(event.src_path)
        if file_path.suffix != ".json":
            return

        # Extract meeting name from filename
        meeting_name = file_path.stem

        # Check if file still exists (it might have been moved to vector DB)
        if not file_path.exists():
            logger.debug(f"File '{meeting_name}.json' was deleted/moved (likely stored in vector DB)")
            # Remove watchers for this file since it's been archived
            if meeting_name in self.watched_files:
                self.watched_files.pop(meeting_name, None)
                self.last_known_state.pop(meeting_name, None)
            return

        # Only process if someone is watching this file
        if meeting_name not in self.watched_files:
            logger.debug(f"File '{meeting_name}.json' changed but no watchers")
            return


        # Small delay to ensure file write is complete
        import time
        time.sleep(0.15)  # Slightly longer delay to ensure file is fully written

        try:
            # Read the updated file
            with open(file_path, "r", encoding="utf-8") as f:
                new_data = json.load(f)

            # Get last known state
            last_state = self.last_known_state.get(
                meeting_name, {"transcripts": [], "total_entries": 0}
            )
            last_transcripts = last_state.get("transcripts", [])
            new_transcripts = new_data.get("transcripts", [])

            # Find new entries (entries that weren't in the last state)
            last_count = len(last_transcripts)
            new_count = len(new_transcripts)


            if new_count > last_count:
                # New entries added - send them to watching clients
                new_entries = new_transcripts[last_count:]
                logger.info(
                    f"📝 Watchdog: Detected {len(new_entries)} NEW transcript entries in '{meeting_name}' - sending to frontend"
                )

                # Update last known state
                self.last_known_state[meeting_name] = new_data

                # Send new entries to all watching WebSockets
                self._send_updates_to_watchers(meeting_name, new_entries)
            elif new_count == last_count and new_transcripts != last_transcripts:
                # Same count but content changed (likely an update to last entry or interim update)
                # Check if the last entry was updated
                if new_transcripts and last_transcripts:
                    last_new = new_transcripts[-1]
                    last_old = last_transcripts[-1]
                    if last_new != last_old:
                        # Last entry was updated (interim or final)
                        logger.info(
                            f"📝 Watchdog: Detected UPDATE to last transcript entry in '{meeting_name}': {last_new.get('speaker', 'Unknown')} - {last_new.get('text', '')[:50]}... (final={last_new.get('is_final', False)}) - sending to frontend"
                        )
                        self.last_known_state[meeting_name] = new_data
                        self._send_updates_to_watchers(
                            meeting_name, [last_new], is_update=True
                        )
                    else:
                        # Check if any entries changed (for interim updates that replace entries)
                        changed_entries = []
                        for i, (old_entry, new_entry) in enumerate(zip(last_transcripts, new_transcripts)):
                            if old_entry != new_entry:
                                changed_entries.append(new_entry)
                        if changed_entries:
                            logger.info(
                                f"📝 Watchdog: Detected {len(changed_entries)} UPDATED transcript entries in '{meeting_name}' - sending to frontend"
                            )
                            self.last_known_state[meeting_name] = new_data
                            self._send_updates_to_watchers(
                                meeting_name, changed_entries, is_update=True
                            )
                else:
                    # No last transcripts but new ones exist - send all
                    if new_transcripts:
                        logger.info(
                            f"📝 Watchdog: Detected new transcript data in '{meeting_name}' (no previous state) - sending all {len(new_transcripts)} entries to frontend"
                        )
                        self.last_known_state[meeting_name] = new_data
                        self._send_updates_to_watchers(meeting_name, new_transcripts)
            elif new_count < last_count:
                self.last_known_state[meeting_name] = new_data

        except FileNotFoundError:
            logger.debug(f"⚠️ Watchdog: File '{meeting_name}.json' was deleted during processing (likely moved to vector DB)")
            # Clean up watchers for this file
            if meeting_name in self.watched_files:
                self.watched_files.pop(meeting_name, None)
                self.last_known_state.pop(meeting_name, None)
        except json.JSONDecodeError as e:
            logger.warning(f"⚠️ Watchdog: JSON decode error for '{meeting_name}': {e} - file might be partially written")
        except Exception as e:
            logger.error(f"❌ Watchdog: Error processing file change for '{meeting_name}': {e}", exc_info=True)

    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        """Set the event loop to use for sending updates from file watcher thread"""
        self.event_loop = loop

    def _send_updates_to_watchers(
        self, meeting_name: str, new_entries: List[Dict], is_update: bool = False
    ):
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
            "is_update": is_update,
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
            self._async_send_updates(watchers, message, meeting_name), self.event_loop
        )

    async def _async_send_updates(
        self, watchers: List[WebSocket], message: Dict, meeting_name: str
    ):
        """Async helper to send updates to watchers - only to users who own the transcript"""
        # Get user_id for this room
        room_user_id = get_user_id_for_room(meeting_name)
        
        disconnected = set()
        for websocket in watchers:
            try:
                # Verify user ownership before sending
                watcher_user_id = self.transcript_manager.get_user_id_for_connection(websocket)
                if room_user_id and watcher_user_id != room_user_id:
                    # This watcher doesn't own the transcript - remove them from watchers
                    logger.warning(
                        f"⚠️  Removing watcher (user_id={watcher_user_id}) for room {meeting_name} owned by user {room_user_id}"
                    )
                    self.remove_watcher(meeting_name, websocket)
                    continue
                
                # Send update only if user owns the transcript or room_user_id is not set (backward compatibility)
                if room_user_id is None or watcher_user_id == room_user_id:
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
        self.connection_users: Dict[WebSocket, int] = {}  # Map WebSocket to user_id
        self.user_transcripts: Dict[int, List[Tuple[str, str, bool]]] = {}  # Per-user transcripts
        self.speaker_label_map: Dict[str, str] = {}
        self.lock = asyncio.Lock()
        self.file_watcher = TranscriptFileWatcher(self)
        self.observer: Optional[Observer] = None

    async def connect(self, websocket: WebSocket, user_id: int):
        await websocket.accept()
        self.connections.add(websocket)
        self.connection_users[websocket] = user_id
        
        # Initialize user transcripts if not exists
        if user_id not in self.user_transcripts:
            self.user_transcripts[user_id] = []
        
        logger.info(f"Client connected (user_id={user_id}). Total connections: {len(self.connections)}")

        # Send existing transcripts for this user only
        user_transcripts = self.user_transcripts.get(user_id, [])
        if user_transcripts:
            await websocket.send_json(
                {
                    "type": "initial_transcripts",
                    "transcripts": [
                        {"speaker": sp, "text": txt, "is_final": is_final}
                        for sp, txt, is_final in user_transcripts
                    ],
                }
            )

    def disconnect(self, websocket: WebSocket):
        self.connections.discard(websocket)
        # Remove user mapping
        if websocket in self.connection_users:
            del self.connection_users[websocket]
        # Remove from all file watchers
        self.file_watcher.remove_all_watchers_for_websocket(websocket)
        logger.info(f"Client disconnected. Total connections: {len(self.connections)}")
    
    def get_user_id_for_connection(self, websocket: WebSocket) -> Optional[int]:
        """Get user_id for a WebSocket connection"""
        return self.connection_users.get(websocket)
    
    def get_connections_for_user(self, user_id: int) -> List[WebSocket]:
        """Get all WebSocket connections for a specific user"""
        return [ws for ws, uid in self.connection_users.items() if uid == user_id]

    def start_file_observer(self):
        """Start the file system observer to watch transcript files"""
        if self.observer is None:
            self.observer = Observer()
            self.observer.schedule(
                self.file_watcher, str(TRANSCRIPTS_DIR), recursive=False
            )
            self.observer.start()
            logger.info(
                f"👁️  Started file observer for transcript directory: {TRANSCRIPTS_DIR}"
            )

    def stop_file_observer(self):
        """Stop the file system observer"""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None
            logger.info("👁️  Stopped file observer")

    async def broadcast_transcript(
        self,
        speaker: str,
        text: str,
        is_final: bool = True,
        meeting_name: Optional[str] = None,
        user_id: Optional[int] = None,
    ):
        """Broadcast a transcript to connected clients, filtered by user_id"""
        async with self.lock:
            text_stripped = text.strip()
            if not text_stripped:
                # Skip empty text
                return

            # Store transcript per user
            if user_id is None:
                logger.warning("broadcast_transcript called without user_id - skipping storage")
                return
            
            # Initialize user transcripts if not exists
            if user_id not in self.user_transcripts:
                self.user_transcripts[user_id] = []
            
            user_transcripts = self.user_transcripts[user_id]
            is_duplicate = False
            
            if is_final:
                # Check if this is an update to the last transcript from the same speaker
                updated_existing = False

                if user_transcripts:
                    last_speaker, last_text, last_is_final = user_transcripts[-1]
                    if speaker == last_speaker:
                        if not last_is_final:
                            # Converting interim to final - update existing entry
                            user_transcripts[-1] = (speaker, text_stripped, is_final)
                            updated_existing = True
                        elif last_text == text_stripped:
                            # Exact duplicate - skip adding
                            logger.debug(
                                f"⏭️  Skipping duplicate broadcast transcript: {speaker} - {text_stripped[:30]}..."
                            )
                            is_duplicate = True
                        elif last_text in text_stripped and len(text_stripped) > len(
                            last_text
                        ):
                            # Both final, text is extension - update existing entry
                            user_transcripts[-1] = (speaker, text_stripped, is_final)
                            updated_existing = True
                        else:
                            # Check if this exact text already exists in recent entries (prevent repeats)
                            # Check last 20 entries to catch duplicates (increased from 3)
                            for entry in user_transcripts[-20:]:
                                entry_speaker, entry_text, entry_is_final = entry
                                if (
                                    entry_speaker == speaker
                                    and entry_text == text_stripped
                                    and entry_is_final
                                ):
                                    is_duplicate = True
                                    logger.debug(
                                        f"⏭️  Skipping duplicate broadcast transcript (found in recent entries): {speaker} - {text_stripped[:30]}..."
                                    )
                                    break
                    else:
                        # Different speaker - check if this exact text already exists in recent entries
                        # Check last 20 entries to catch duplicates (increased from 3)
                        for entry in user_transcripts[-20:]:
                            entry_speaker, entry_text, entry_is_final = entry
                            if (
                                entry_speaker == speaker
                                and entry_text == text_stripped
                                and entry_is_final
                            ):
                                is_duplicate = True
                                logger.debug(
                                    f"⏭️  Skipping duplicate broadcast transcript (different speaker, found in recent entries): {speaker} - {text_stripped[:30]}..."
                                )
                                break

                if not updated_existing and not is_duplicate:
                    user_transcripts.append((speaker, text_stripped, is_final))
            else:
                # For interim transcripts, update last entry if same speaker, or append new
                updated_existing = False
                if user_transcripts:
                    last_speaker, last_text, last_is_final = user_transcripts[-1]
                    if speaker == last_speaker and not last_is_final:
                        # Update existing interim entry
                        user_transcripts[-1] = (speaker, text_stripped, is_final)
                        updated_existing = True

                if not updated_existing:
                    user_transcripts.append((speaker, text_stripped, is_final))

        # Broadcast to all connected clients for this user only
        # Skip only final duplicates, but always broadcast interim transcripts (even if duplicate)
        # This ensures real-time updates are visible during recording
        if is_final and is_duplicate:
            # Don't broadcast duplicate final transcripts
            return

        message = {
            "type": "transcript",
            "speaker": speaker,
            "text": text_stripped,
            "is_final": is_final,
            "meeting_name": meeting_name,
        }

        # Get connections for this user only
        user_connections = self.get_connections_for_user(user_id) if user_id else []

        logger.debug(
            f"Broadcasting transcript to user_id={user_id}: {speaker} - {text_stripped[:50]}... (final={is_final}, connections={len(user_connections)})"
        )

        if len(user_connections) == 0:
            logger.debug(f"No WebSocket connections available for user_id={user_id} to send transcript to!")

        disconnected = set()
        for connection in user_connections:
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

    async def update_transcripts(self, speaker: str, text: str, is_final: bool = True, user_id: Optional[int] = None):
        """Update internal transcript list without broadcasting (for accumulation) - requires user_id"""
        if user_id is None:
            logger.warning("update_transcripts called without user_id - skipping")
            return
            
        async with self.lock:
            text_stripped = text.strip()
            if not text_stripped:
                # Skip empty text
                return

            # Initialize user transcripts if not exists
            if user_id not in self.user_transcripts:
                self.user_transcripts[user_id] = []

            user_transcripts = self.user_transcripts[user_id]
            
            # Check if this is an update to the last transcript from the same speaker
            updated_existing = False
            is_duplicate = False

            if user_transcripts:
                last_speaker, last_text, last_is_final = user_transcripts[-1]
                if speaker == last_speaker:
                    if not is_final and not last_is_final:
                        # Both interim - update existing entry
                        user_transcripts[-1] = (speaker, text_stripped, is_final)
                        updated_existing = True
                    elif is_final and not last_is_final:
                        # Converting interim to final - update existing entry
                        user_transcripts[-1] = (speaker, text_stripped, is_final)
                        updated_existing = True
                    elif is_final and last_is_final:
                        # Both final - check for duplicates or extensions
                        if last_text == text_stripped:
                            # Exact duplicate - skip adding
                            logger.debug(
                                f"⏭️  Skipping duplicate transcript in manager: {speaker} - {text_stripped[:30]}..."
                            )
                            is_duplicate = True
                        elif last_text in text_stripped and len(text_stripped) > len(
                            last_text
                        ):
                            # Text is extension - update existing entry
                            user_transcripts[-1] = (speaker, text_stripped, is_final)
                            updated_existing = True
                        else:
                            # Check if this exact text already exists in recent entries (prevent repeats)
                            for entry in user_transcripts[-3:]:
                                entry_speaker, entry_text, entry_is_final = entry
                                if (
                                    entry_speaker == speaker
                                    and entry_text == text_stripped
                                    and entry_is_final
                                ):
                                    is_duplicate = True
                                    logger.debug(
                                        f"⏭️  Skipping duplicate transcript in manager (found in recent entries): {speaker} - {text_stripped[:30]}..."
                                    )
                                    break
                else:
                    # Different speaker - check if this exact text already exists in recent entries
                    for entry in user_transcripts[-3:]:
                        entry_speaker, entry_text, entry_is_final = entry
                        if (
                            entry_speaker == speaker
                            and entry_text == text_stripped
                            and entry_is_final
                        ):
                            is_duplicate = True
                            logger.debug(
                                f"⏭️  Skipping duplicate transcript in manager (different speaker, found in recent entries): {speaker} - {text_stripped[:30]}..."
                            )
                            break

            if not updated_existing and not is_duplicate:
                user_transcripts.append((speaker, text_stripped, is_final))

    async def send_complete_transcript(
        self, meeting_title: str, transcript_list: List[Tuple[str, str]] = None, user_id: Optional[int] = None
    ):
        """Send complete transcript to connected clients for a specific user when recording stops"""
        async with self.lock:
            # Get user_id from room mapping if not provided
            if user_id is None:
                user_id = get_user_id_for_room(meeting_title)
            
            if user_id is None:
                logger.warning(f"Cannot send complete transcript for {meeting_title}: no user_id found")
                return

            # Use provided transcript_list or fall back to user-specific transcripts
            if transcript_list is None:
                user_transcripts = self.user_transcripts.get(user_id, [])
                transcript_list = [(sp, txt) for sp, txt, _ in user_transcripts]

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
                "transcripts": transcript_data,
            }

            # Get connections for this user only
            user_connections = self.get_connections_for_user(user_id)
            
            logger.info(
                f"Sending complete transcript: {meeting_title} with {len(transcript_data)} entries to user_id={user_id} (connections={len(user_connections)})"
            )

            if len(user_connections) == 0:
                logger.warning(
                    f"No WebSocket connections available for user_id={user_id} to send complete transcript to!"
                )

            disconnected = set()
            for connection in user_connections:
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
    # Initialize database tables
    try:
        init_db()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error(f"❌ Database initialization error: {e}")
        logger.error("⚠️  Server will start but authentication features may not work properly.")
        logger.error("⚠️  Please check your DATABASE_URL in .env.local and ensure PostgreSQL is running.")
    
    # Initialize vector database index
    try:
        from vector_db.vector_store import init_vector_index
        if init_vector_index():
            logger.info("✅ Vector database index initialized")
        else:
            logger.warning("⚠️  Vector database index initialization failed")
            logger.warning("⚠️  Transcripts will be stored in JSON files only. Check Redis connection.")
    except ImportError as e:
        logger.warning(f"⚠️  Vector DB modules not available: {e}")
        logger.warning("⚠️  Install redis and sentence-transformers to enable vector storage.")
    except Exception as e:
        logger.warning(f"⚠️  Vector DB initialization error: {e}")
        logger.warning("⚠️  Transcripts will be stored in JSON files only. Check Redis connection.")
    
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

# JWT Security
security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    """Dependency to get current authenticated user"""
    token = credentials.credentials
    payload = verify_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    username: str = payload.get("sub")
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = get_user_by_username(db, username=username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


@app.get("/")
async def root():
    """Root endpoint - returns API information"""
    return {
        "message": "Transcript API Server",
        "status": "running",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "database_health": "/health/db",
            "authentication": {
                "signup": "POST /auth/signup",
                "login": "POST /auth/login",
                "current_user": "GET /auth/me"
            },
            "transcripts": {
                "list": "GET /transcripts/list",
                "get": "GET /transcripts?meeting_name=<name>",
                "update": "POST /transcripts/update"
            },
            "livekit": {
                "token": "POST /token"
            },
            "websocket": "WS /ws/transcripts"
        },
        "docs": "/docs"
    }


@app.get("/api/endpoints")
async def list_endpoints():
    """List all available API endpoints"""
    endpoints = {
        "authentication": [
            {
                "method": "POST",
                "path": "/auth/signup",
                "description": "Register a new user",
                "body": {"username": "string", "email": "string", "password": "string"},
                "response": "TokenResponse with access_token and user info"
            },
            {
                "method": "POST",
                "path": "/auth/login",
                "description": "Authenticate user and get JWT token",
                "body": {"username": "string", "password": "string"},
                "response": "TokenResponse with access_token and user info"
            },
            {
                "method": "GET",
                "path": "/auth/me",
                "description": "Get current authenticated user information",
                "auth_required": True,
                "response": "User object"
            }
        ],
        "health": [
            {
                "method": "GET",
                "path": "/health",
                "description": "Check API server health"
            },
            {
                "method": "GET",
                "path": "/health/db",
                "description": "Check database connection"
            }
        ],
        "transcripts": [
            {
                "method": "GET",
                "path": "/transcripts/list",
                "description": "List all available transcripts",
                "auth_required": True
            },
            {
                "method": "GET",
                "path": "/transcripts?meeting_name=<name>",
                "description": "Get transcript for a specific meeting",
                "auth_required": True,
                "query_params": {"meeting_name": "string (optional)"}
            },
            {
                "method": "POST",
                "path": "/transcripts/update",
                "description": "Update transcripts from main.py process",
                "body": {"transcripts": "array", "room_name": "string"}
            },
            {
                "method": "GET",
                "path": "/transcripts/vector",
                "description": "Get transcript from vector database by username and meeting name",
                "auth_required": True,
                "query_params": {
                    "username": "string (required)",
                    "meeting_name": "string (required)"
                },
                "response": "Transcript object with meeting_id, meeting_name, user_id, username, timestamp, speakers, and transcript_text"
            }
        ],
        "livekit": [
            {
                "method": "POST",
                "path": "/token",
                "description": "Generate LiveKit access token for a room",
                "auth_required": True,
                "body": {"room_name": "string", "identity": "string (optional)"}
            }
        ],
        "websocket": [
            {
                "method": "WS",
                "path": "/ws/transcripts",
                "description": "WebSocket connection for real-time transcript updates"
            }
        ]
    }
    return {
        "endpoints": endpoints,
        "base_url": "http://localhost:8000",
        "documentation": "/docs",
        "openapi_spec": "/openapi.json"
    }


@app.get("/health/db")
async def check_database(db: Session = Depends(get_db)):
    """Check database connection"""
    try:
        # Try a simple query
        from database.models import User
        db.query(User).first()
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database connection failed: {str(e)}"
        )


@app.get("/health/vector-db")
async def check_vector_db():
    """Check Redis vector database connection"""
    try:
        from vector_db.vector_store import get_redis_client
        client = get_redis_client()
        client.ping()
        
        # Count transcripts
        keys = client.keys("transcript:*")
        return {
            "status": "healthy",
            "vector_db": "connected",
            "transcript_count": len(keys)
        }
    except ImportError as e:
        error_msg = str(e)
        if "tensorflow" in error_msg.lower() or "sentence" in error_msg.lower():
            return {
                "status": "unhealthy",
                "vector_db": "module_import_error",
                "error": "TensorFlow/sentence-transformers import failed",
                "message": "Vector DB module cannot be loaded due to dependency issues. Check TensorFlow installation.",
                "solution": "Try: pip install --upgrade tensorflow sentence-transformers or fix TensorFlow library conflicts"
            }
        return {
            "status": "unhealthy",
            "vector_db": "module_import_error",
            "error": str(e),
            "message": "Vector DB module cannot be imported."
        }
    except Exception as e:
        error_str = str(e)
        # Check if it's a Redis connection error
        if "connection" in error_str.lower() or "redis" in error_str.lower() or "Connection refused" in error_str:
            return {
                "status": "unhealthy",
                "vector_db": "disconnected",
                "error": error_str,
                "message": "Redis is not running. Start Redis with: redis-server or docker run -d -p 6379:6379 redis/redis-stack"
            }
        # Check if it's a TensorFlow import error (might be caught as generic Exception)
        if "tensorflow" in error_str.lower() or "dlopen" in error_str.lower() or "Symbol not found" in error_str:
            return {
                "status": "unhealthy",
                "vector_db": "module_import_error",
                "error": "TensorFlow library loading failed",
                "message": "TensorFlow native libraries cannot be loaded. This is often due to incompatible system libraries.",
                "solution": "Try: pip install --upgrade tensorflow or use a conda environment with compatible libraries"
            }
        return {
            "status": "unhealthy",
            "vector_db": "disconnected",
            "error": str(e),
            "message": "Redis is not running. Start Redis with: redis-server or docker run -d -p 6379:6379 redis/redis-stack"
        }
    except Exception as e:
        logger.error(f"Vector DB health check failed: {e}")
        return {
            "status": "unhealthy",
            "vector_db": "error",
            "error": str(e),
            "message": "Vector DB check failed. Check Redis connection and dependencies."
        }


# Authentication endpoints
class UserSignup(BaseModel):
    username: str
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: dict


@app.post("/auth/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def signup(user_data: UserSignup, db: Session = Depends(get_db)):
    """Register a new user"""
    # Check if username already exists
    if get_user_by_username(db, user_data.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    # Check if email already exists
    if get_user_by_email(db, user_data.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create new user
    try:
        user = create_user(
            db,
            username=user_data.username,
            email=user_data.email,
            password=user_data.password
        )
        
        # Create access token
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user.username}, expires_delta=access_token_expires
        )
        
        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            user={
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "is_active": user.is_active
            }
        )
    except Exception as e:
        logger.error(f"Error creating user: {e}", exc_info=True)
        error_detail = str(e)
        # Check if it's a database connection error
        if "connection" in error_detail.lower() or "database" in error_detail.lower():
            error_detail = "Database connection error. Please check your database configuration."
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating user: {error_detail}"
        )


@app.post("/auth/login", response_model=TokenResponse)
async def login(user_data: UserLogin, db: Session = Depends(get_db)):
    """Authenticate user and return JWT token"""
    user = authenticate_user(db, user_data.username, user_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )
    
    # Create access token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user={
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_active": user.is_active
        }
    )


@app.get("/auth/me")
async def get_current_user_info(current_user = Depends(get_current_user)):
    """Get current authenticated user information"""
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "is_active": current_user.is_active,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None
    }



@app.get("/health")
async def health():
    # Calculate total transcripts across all users
    total_transcripts = sum(
        len(transcripts) 
        for transcripts in transcript_manager.user_transcripts.values()
    )
    return {
        "status": "healthy",
        "websocket_endpoint": "/ws/transcripts",
        "active_connections": len(transcript_manager.connections),
        "total_transcripts": total_transcripts,
    }


@app.get("/transcripts")
async def get_transcripts(
    meeting_name: Optional[str] = Query(
        None, description="Meeting name to retrieve transcript for"
    ),
    current_user = Depends(get_current_user),
):
    """
    Get transcripts - first try vector DB, then fall back to JSON file (for active recordings)
    """
    if meeting_name:
        # First, try to get from vector database
        try:
            from vector_db.vector_store import get_redis_client
            import json
            
            client = get_redis_client()
            keys = client.keys("transcript:*")
            
            # Search for matching transcript by meeting_name and user_id
            for key in keys:
                data = client.hgetall(key)
                stored_meeting_name = data.get(b'meeting_name')
                stored_user_id = data.get(b'user_id')
                
                if stored_meeting_name and stored_user_id:
                    stored_meeting_name_str = stored_meeting_name.decode('utf-8')
                    stored_user_id_str = int(stored_user_id.decode('utf-8'))
                    
                    if stored_meeting_name_str == meeting_name and stored_user_id_str == current_user.id:
                        # Found in vector DB - parse transcript_text back to transcript entries
                        transcript_text = data.get(b'transcript_text', b'').decode('utf-8')
                        speakers_str = data.get(b'speakers', b'[]').decode('utf-8')
                        speakers = json.loads(speakers_str)
                        
                        # Parse transcript_text back to individual entries
                        # Format: "Speaker 1: text\nSpeaker 2: text"
                        transcript_entries = []
                        for line in transcript_text.split('\n'):
                            if ':' in line:
                                parts = line.split(':', 1)
                                if len(parts) == 2:
                                    speaker = parts[0].strip()
                                    text = parts[1].strip()
                                    if text:
                                        transcript_entries.append({
                                            "speaker": speaker,
                                            "text": text,
                                            "is_final": True
                                        })
                        
                        return {
                            "meeting_name": stored_meeting_name_str,
                            "transcripts": transcript_entries,
                            "total_entries": len(transcript_entries),
                            "source": "vector_db"
                        }
        except Exception as e:
            logger.warning(f"Error fetching from vector DB, trying JSON file: {e}")
        
        # Fall back to JSON file (for active recordings that haven't been stored yet)
        transcript_data = load_transcript_from_file(meeting_name)
        if transcript_data:
            transcript_data["source"] = "json_file"
            return transcript_data
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Transcript not found for meeting: {meeting_name}",
            )
    else:
        # Return from memory (backward compatibility for active recording)
        # Get transcripts for current user only
        user_transcripts = transcript_manager.user_transcripts.get(current_user.id, [])
        return {
            "transcripts": [
                {"speaker": sp, "text": txt, "is_final": is_final}
                for sp, txt, is_final in user_transcripts
            ],
            "speaker_labels": transcript_manager.speaker_label_map,
            "source": "memory"
        }


@app.get("/transcripts/list")
async def list_all_transcripts(current_user = Depends(get_current_user)):
    """List all available transcripts from vector database for current user"""
    try:
        transcript_list = []
        meeting_transcripts = {}  # meeting_name -> transcript_data (for deduplication)
        
        # Get transcripts from vector database
        try:
            from vector_db.vector_store import get_redis_client
            import json
            
            client = get_redis_client()
            keys = client.keys("transcript:*")
            
            # Filter transcripts for current user and deduplicate by meeting_name
            # Use a dict to track the most recent transcript for each meeting_name
            
            for key in keys:
                data = client.hgetall(key)
                stored_user_id = data.get(b'user_id')
                
                if stored_user_id and int(stored_user_id.decode('utf-8')) == current_user.id:
                    meeting_name = data.get(b'meeting_name', b'').decode('utf-8')
                    timestamp = int(data.get(b'timestamp', b'0').decode('utf-8'))
                    transcript_text = data.get(b'transcript_text', b'').decode('utf-8')
                    
                    # Count entries (lines with speaker: text format)
                    entry_count = len([line for line in transcript_text.split('\n') if ':' in line and line.split(':', 1)[1].strip()])
                    
                    transcript_data = {
                        "meeting_name": meeting_name,
                        "file_name": meeting_name,  # Keep for backward compatibility
                        "total_entries": entry_count,
                        "last_modified": timestamp,  # Use timestamp as last_modified
                        "source": "vector_db"
                    }
                    
                    # Keep only the most recent transcript for each meeting_name
                    if meeting_name not in meeting_transcripts:
                        meeting_transcripts[meeting_name] = transcript_data
                    else:
                        # If this transcript is newer, replace the old one
                        if timestamp > meeting_transcripts[meeting_name]["last_modified"]:
                            meeting_transcripts[meeting_name] = transcript_data
            
            # Convert dict to list
            transcript_list = list(meeting_transcripts.values())
        except Exception as e:
            logger.warning(f"Error fetching from vector DB: {e}")
        
        # Also check JSON files (for active recordings that haven't been stored yet)
        if TRANSCRIPTS_DIR.exists():
            for file_path in TRANSCRIPTS_DIR.glob("*.json"):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        meeting_name = file_path.stem
                        
                        # Check if this meeting is already in vector DB
                        already_in_db = meeting_name in meeting_transcripts
                        
                        if not already_in_db:
                            transcript_list.append({
                                "meeting_name": data.get("meeting_name", meeting_name),
                                "file_name": meeting_name,
                                "total_entries": data.get("total_entries", 0),
                                "last_modified": file_path.stat().st_mtime,
                                "source": "json_file"
                            })
                except Exception as e:
                    logger.warning(f"Error reading transcript file {file_path}: {e}")
                    continue

        # Sort by last modified (newest first)
        transcript_list.sort(key=lambda x: x.get("last_modified", 0), reverse=True)

        logger.info(f"📋 Listed {len(transcript_list)} unique transcripts (from vector DB and JSON files)")
        return {"transcripts": transcript_list, "count": len(transcript_list)}
    except Exception as e:
        logger.error(f"Error listing transcripts: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error listing transcripts: {str(e)}"
        )


@app.post("/transcripts/cleanup-duplicates")
async def cleanup_duplicate_transcripts(current_user = Depends(get_current_user)):
    """Remove duplicate transcripts, keeping only the most recent one for each meeting_name"""
    try:
        from vector_db.vector_store import get_redis_client
        import json
        
        client = get_redis_client()
        keys = client.keys("transcript:*")
        
        # Group transcripts by meeting_name
        meeting_groups = {}  # meeting_name -> list of (key, timestamp)
        
        for key in keys:
            data = client.hgetall(key)
            stored_user_id = data.get(b'user_id')
            
            if stored_user_id and int(stored_user_id.decode('utf-8')) == current_user.id:
                meeting_name = data.get(b'meeting_name', b'').decode('utf-8')
                timestamp = int(data.get(b'timestamp', b'0').decode('utf-8'))
                
                if meeting_name not in meeting_groups:
                    meeting_groups[meeting_name] = []
                meeting_groups[meeting_name].append((key.decode('utf-8'), timestamp))
        
        # Delete duplicates, keeping only the most recent
        deleted_count = 0
        for meeting_name, transcripts in meeting_groups.items():
            if len(transcripts) > 1:
                # Sort by timestamp (newest first)
                transcripts.sort(key=lambda x: x[1], reverse=True)
                # Keep the first (most recent), delete the rest
                for key, _ in transcripts[1:]:
                    client.delete(key)
                    deleted_count += 1
                    logger.info(f"🗑️  Deleted duplicate transcript: {key}")
        
        return {
            "status": "success",
            "deleted_count": deleted_count,
            "message": f"Removed {deleted_count} duplicate transcript(s)"
        }
    except Exception as e:
        logger.error(f"Error cleaning up duplicates: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error cleaning up duplicates: {str(e)}"
        )


@app.get("/transcripts/vector")
async def get_vector_transcript(
    username: str = Query(..., description="Username to get transcript for"),
    meeting_name: str = Query(..., description="Meeting name to get transcript for"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Get transcript from vector database by username and meeting name.
    Requires authentication - only the transcript owner or admin can access.
    """
    try:
        # Get user by username
        user = get_user_by_username(db, username=username)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User '{username}' not found"
            )
        
        user_id = user.id
        
        # Check if current user has permission (own transcript or admin)
        if current_user.id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only access your own transcripts"
            )
        
        # Get Redis client
        from vector_db.vector_store import get_redis_client
        import json
        
        client = get_redis_client()
        
        # Get all transcript keys
        keys = client.keys("transcript:*")
        
        # Search for matching transcript
        transcript = None
        for key in keys:
            # Get hash data (Redis returns bytes when decode_responses=False)
            data = client.hgetall(key)
            
            # Check if this transcript matches user_id and meeting_name
            stored_user_id = data.get(b'user_id')
            stored_meeting_name = data.get(b'meeting_name')
            
            if stored_user_id and stored_meeting_name:
                stored_user_id_str = stored_user_id.decode('utf-8')
                stored_meeting_name_str = stored_meeting_name.decode('utf-8')
                
                if int(stored_user_id_str) == user_id and stored_meeting_name_str == meeting_name:
                    # Found matching transcript
                    transcript = {
                        "meeting_id": data.get(b'meeting_id', b'').decode('utf-8'),
                        "meeting_name": stored_meeting_name_str,
                        "user_id": user_id,
                        "username": username,
                        "timestamp": int(data.get(b'timestamp', b'0').decode('utf-8')),
                        "speakers": json.loads(data.get(b'speakers', b'[]').decode('utf-8')),
                        "transcript_text": data.get(b'transcript_text', b'').decode('utf-8'),
                    }
                    break
        
        if transcript is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Transcript not found for user '{username}' and meeting '{meeting_name}'"
            )
        
        logger.info(
            f"Retrieved vector transcript: user={username}, meeting={meeting_name}"
        )
        
        return transcript
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving vector transcript: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving transcript: {str(e)}"
        )


class TranscriptUpdateRequest(BaseModel):
    transcripts: List[Tuple[str, str]]
    room_name: str


@app.post("/transcripts/update")
async def update_transcripts_from_main(request: TranscriptUpdateRequest):
    """Update transcripts from main.py process and save to file"""
    logger.info(
        f"Received transcript update from main.py: {len(request.transcripts)} transcripts for room {request.room_name}"
    )
    
    # Get user_id from room mapping
    user_id = get_user_id_for_room(request.room_name)
    if user_id is None:
        logger.warning(
            f"No user_id found for room {request.room_name}, cannot update transcripts"
        )
        return {
            "status": "error",
            "message": "No user_id found for this room",
            "meeting_name": request.room_name,
        }
    
    # Update user-specific transcripts
    async with transcript_manager.lock:
        # Initialize user transcripts if not exists
        if user_id not in transcript_manager.user_transcripts:
            transcript_manager.user_transcripts[user_id] = []
        
        transcript_manager.user_transcripts[user_id] = [
            (speaker, text, True) for speaker, text in request.transcripts
        ]

    # Save to file
    if request.transcripts:
        save_transcript_to_file(request.room_name, request.transcripts)

    logger.info(
        f"Updated transcript manager for user_id={user_id} with {len(transcript_manager.user_transcripts[user_id])} transcripts"
    )
    return {
        "status": "ok",
        "count": len(transcript_manager.user_transcripts[user_id]),
        "meeting_name": request.room_name,
        "user_id": user_id,
    }


class TokenRequest(BaseModel):
    room_name: str
    identity: Optional[str] = None


class StopRecordingRequest(BaseModel):
    meeting_name: str


@app.post("/transcripts/stop-recording")
async def stop_recording(
    request: StopRecordingRequest,
    current_user = Depends(get_current_user)
):
    """
    Stop recording: Store transcript to vector DB and delete JSON file.
    Called when user clicks stop recording button.
    """
    meeting_name = request.meeting_name
    user_id = current_user.id
    
    # Verify user owns this meeting
    room_user_id = get_user_id_for_room(meeting_name)
    if room_user_id and room_user_id != user_id:
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to stop this recording"
        )
    
    file_path = get_transcript_file_path(meeting_name)
    
    if not file_path.exists():
        return {
            "status": "error",
            "message": f"Transcript file not found for meeting: {meeting_name}",
            "meeting_name": meeting_name
        }
    
    try:
        # Load transcript from JSON file
        transcript_data = load_transcript_from_file(meeting_name, filter_interim=False)
        if not transcript_data:
            return {
                "status": "error",
                "message": f"Failed to load transcript from file",
                "meeting_name": meeting_name
            }
        
        transcripts_list = transcript_data.get("transcripts", [])
        if not transcripts_list:
            # Empty transcript - just delete the file
            try:
                file_path.unlink()
                logger.info(f"🗑️  Deleted empty transcript file: {file_path}")
            except Exception as e:
                logger.warning(f"⚠️  Failed to delete empty JSON file: {e}")
            
            return {
                "status": "ok",
                "message": "Empty transcript file deleted",
                "meeting_name": meeting_name,
                "stored_to_vector_db": False
            }
        
        # Convert to format needed for store_transcript
        transcript_entries = [
            (entry.get("speaker", "Unknown"), entry.get("text", ""))
            for entry in transcripts_list
            if entry.get("text", "").strip()  # Only non-empty entries
        ]
        
        if not transcript_entries:
            # No valid entries - delete file
            try:
                file_path.unlink()
                logger.info(f"🗑️  Deleted transcript file with no valid entries: {file_path}")
            except Exception as e:
                logger.warning(f"⚠️  Failed to delete JSON file: {e}")
            
            return {
                "status": "ok",
                "message": "Transcript file deleted (no valid entries)",
                "meeting_name": meeting_name,
                "stored_to_vector_db": False
            }
        
        # Store to vector DB and delete JSON file
        try:
            from vector_db.vector_store import store_transcript, get_redis_client
            from datetime import datetime
            import uuid
            
            # Get user_id (use room mapping if available, otherwise use current user)
            storage_user_id = room_user_id if room_user_id else user_id
            
            # Check if transcript with same meeting_name already exists
            client = get_redis_client()
            keys = client.keys("transcript:*")
            existing_meeting_id = None
            
            for key in keys:
                data = client.hgetall(key)
                stored_meeting_name = data.get(b'meeting_name')
                stored_user_id = data.get(b'user_id')
                
                if stored_meeting_name and stored_user_id:
                    stored_meeting_name_str = stored_meeting_name.decode('utf-8')
                    stored_user_id_str = int(stored_user_id.decode('utf-8'))
                    
                    if stored_meeting_name_str == meeting_name and stored_user_id_str == storage_user_id:
                        existing_meeting_id = key.decode('utf-8').replace('transcript:', '')
                        break
            
            # Generate meeting_id
            timestamp = datetime.now().timestamp()
            meeting_id = existing_meeting_id if existing_meeting_id else f"{storage_user_id}_{meeting_name}_{int(timestamp)}"
            
            # Combine transcript entries into text
            transcript_text_parts = []
            speakers_set = set()
            
            for speaker, text in transcript_entries:
                if text.strip():
                    transcript_text_parts.append(f"{speaker}: {text.strip()}")
                    speakers_set.add(speaker)
            
            transcript_text = "\n".join(transcript_text_parts)
            speakers_list = sorted(list(speakers_set))
            
            if transcript_text:
                # Store in vector DB
                logger.info(f"📊 Storing transcript in vector DB: {meeting_name}")
                stored_meeting_id = store_transcript(
                    user_id=storage_user_id,
                    meeting_name=meeting_name,
                    transcript_text=transcript_text,
                    speakers=speakers_list,
                    timestamp=timestamp,
                    meeting_id=meeting_id,
                )
                
                if stored_meeting_id:
                    # Successfully stored - delete JSON file
                    try:
                        file_path.unlink()
                        logger.info(f"🗑️  Deleted JSON file after successful vector DB storage: {file_path}")
                        return {
                            "status": "ok",
                            "message": "Transcript stored in vector database and JSON file deleted",
                            "meeting_name": meeting_name,
                            "stored_to_vector_db": True,
                            "meeting_id": stored_meeting_id
                        }
                    except Exception as e:
                        logger.warning(f"⚠️  Failed to delete JSON file {file_path}: {e}")
                        return {
                            "status": "partial",
                            "message": "Transcript stored in vector DB but failed to delete JSON file",
                            "meeting_name": meeting_name,
                            "stored_to_vector_db": True,
                            "error": str(e)
                        }
                else:
                    logger.error(f"❌ Vector DB storage failed for '{meeting_name}'")
                    return {
                        "status": "error",
                        "message": "Failed to store transcript in vector database",
                        "meeting_name": meeting_name,
                        "stored_to_vector_db": False
                    }
            else:
                # Empty transcript text - just delete file
                try:
                    file_path.unlink()
                    logger.info(f"🗑️  Deleted transcript file (empty text): {file_path}")
                except Exception as e:
                    logger.warning(f"⚠️  Failed to delete JSON file: {e}")
                
                return {
                    "status": "ok",
                    "message": "Transcript file deleted (empty transcript)",
                    "meeting_name": meeting_name,
                    "stored_to_vector_db": False
                }
                
        except ImportError as e:
            logger.warning(f"⚠️  Vector DB modules not available: {e}")
            return {
                "status": "error",
                "message": "Vector DB modules not available",
                "meeting_name": meeting_name,
                "stored_to_vector_db": False
            }
        except Exception as e:
            logger.error(f"❌ Error storing transcript in vector DB: {e}")
            return {
                "status": "error",
                "message": f"Error storing transcript: {str(e)}",
                "meeting_name": meeting_name,
                "stored_to_vector_db": False
            }
            
    except Exception as e:
        logger.error(f"❌ Error in stop_recording endpoint: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to stop recording: {str(e)}"
        )


class UpdateTranscriptRequest(BaseModel):
    transcripts: List[Dict[str, str]]


@app.delete("/transcripts/{meeting_name}")
async def delete_transcript(
    meeting_name: str,
    current_user = Depends(get_current_user)
):
    """
    Delete a transcript - removes from vector DB and deletes JSON file.
    Requires user ownership verification.
    """
    user_id = current_user.id
    
    # Normalize meeting_name: remove .json extension if present
    normalized_meeting_name = meeting_name
    if normalized_meeting_name.endswith('.json'):
        normalized_meeting_name = normalized_meeting_name[:-5]  # Remove .json
    
    logger.info(f"🗑️  Delete request for meeting_name='{meeting_name}' (normalized: '{normalized_meeting_name}') by user_id={user_id}")
    
    # Verify user owns this meeting (try both with and without .json)
    room_user_id = get_user_id_for_room(normalized_meeting_name) or get_user_id_for_room(meeting_name)
    if room_user_id and room_user_id != user_id:
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to delete this transcript"
        )
    
    deleted_from_vector_db = False
    deleted_from_file = False
    deleted_keys = []
    
    # Try to delete from vector database
    try:
        from vector_db.vector_store import get_redis_client
        
        client = get_redis_client()
        keys = client.keys("transcript:*")
        
        logger.info(f"🔍 Searching {len(keys)} transcript keys in vector DB for meeting_name='{normalized_meeting_name}'")
        
        for key in keys:
            data = client.hgetall(key)
            stored_meeting_name = data.get(b'meeting_name')
            stored_user_id = data.get(b'user_id')
            
            if stored_meeting_name and stored_user_id:
                stored_meeting_name_str = stored_meeting_name.decode('utf-8')
                stored_user_id_str = int(stored_user_id.decode('utf-8'))
                
                # Compare both normalized names (with and without .json)
                name_matches = (
                    stored_meeting_name_str == normalized_meeting_name or
                    stored_meeting_name_str == meeting_name or
                    (stored_meeting_name_str.endswith('.json') and stored_meeting_name_str[:-5] == normalized_meeting_name)
                )
                
                if name_matches and stored_user_id_str == user_id:
                    # Found it - delete from Redis
                    key_str = key.decode('utf-8')
                    client.delete(key)
                    deleted_keys.append(key_str)
                    deleted_from_vector_db = True
                    logger.info(f"🗑️  Deleted transcript '{stored_meeting_name_str}' (key: {key_str}) from vector DB")
        
        if deleted_keys:
            logger.info(f"✅ Successfully deleted {len(deleted_keys)} transcript(s) from vector DB: {deleted_keys}")
        else:
            logger.warning(f"⚠️  No matching transcripts found in vector DB for meeting_name='{normalized_meeting_name}' (user_id={user_id})")
            
    except Exception as e:
        logger.error(f"❌ Error deleting from vector DB: {e}", exc_info=True)
    
    # Try to delete JSON file if it exists (try both with and without .json)
    for name_variant in [normalized_meeting_name, meeting_name]:
        file_path = get_transcript_file_path(name_variant)
        if file_path.exists():
            try:
                file_path.unlink()
                deleted_from_file = True
                logger.info(f"🗑️  Deleted transcript file: {file_path}")
                break
            except Exception as e:
                logger.warning(f"⚠️  Failed to delete JSON file {file_path}: {e}")
    
    if deleted_from_vector_db or deleted_from_file:
        return {
            "status": "ok",
            "message": "Transcript deleted successfully",
            "meeting_name": normalized_meeting_name,
            "deleted_from_vector_db": deleted_from_vector_db,
            "deleted_from_file": deleted_from_file,
            "deleted_keys": deleted_keys if deleted_from_vector_db else []
        }
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Transcript '{normalized_meeting_name}' not found in vector DB or file system"
        )


@app.put("/transcripts/{meeting_name}")
async def update_transcript(
    meeting_name: str,
    request: UpdateTranscriptRequest,
    current_user = Depends(get_current_user)
):
    """
    Update a transcript - modifies entries in vector DB and JSON file.
    Requires user ownership verification.
    """
    user_id = current_user.id
    
    # Verify user owns this meeting
    room_user_id = get_user_id_for_room(meeting_name)
    if room_user_id and room_user_id != user_id:
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to update this transcript"
        )
    
    # Convert request transcripts to (speaker, text) tuples
    transcript_entries = [
        (entry.get("speaker", "Unknown"), entry.get("text", ""))
        for entry in request.transcripts
        if entry.get("text", "").strip()  # Only non-empty entries
    ]
    
    if not transcript_entries:
        raise HTTPException(
            status_code=400,
            detail="Cannot update transcript with empty entries"
        )
    
    # Update in vector database
    updated_in_vector_db = False
    try:
        from vector_db.vector_store import store_transcript, get_redis_client
        from datetime import datetime
        
        client = get_redis_client()
        keys = client.keys("transcript:*")
        existing_meeting_id = None
        
        # Find existing transcript
        for key in keys:
            data = client.hgetall(key)
            stored_meeting_name = data.get(b'meeting_name')
            stored_user_id = data.get(b'user_id')
            
            if stored_meeting_name and stored_user_id:
                stored_meeting_name_str = stored_meeting_name.decode('utf-8')
                stored_user_id_str = int(stored_user_id.decode('utf-8'))
                
                if stored_meeting_name_str == meeting_name and stored_user_id_str == user_id:
                    existing_meeting_id = key.decode('utf-8').replace('transcript:', '')
                    break
        
        # Combine transcript entries into text
        transcript_text_parts = []
        speakers_set = set()
        
        for speaker, text in transcript_entries:
            if text.strip():
                transcript_text_parts.append(f"{speaker}: {text.strip()}")
                speakers_set.add(speaker)
        
        transcript_text = "\n".join(transcript_text_parts)
        speakers_list = sorted(list(speakers_set))
        
        # Generate meeting_id if not exists
        timestamp = datetime.now().timestamp()
        meeting_id = existing_meeting_id if existing_meeting_id else f"{user_id}_{meeting_name}_{int(timestamp)}"
        
        # Store/update in vector DB
        stored_meeting_id = store_transcript(
            user_id=user_id,
            meeting_name=meeting_name,
            transcript_text=transcript_text,
            speakers=speakers_list,
            timestamp=timestamp,
            meeting_id=meeting_id,
        )
        
        if stored_meeting_id:
            updated_in_vector_db = True
            logger.info(f"✅ Updated transcript '{meeting_name}' in vector DB")
    except Exception as e:
        logger.warning(f"⚠️  Error updating in vector DB: {e}")
    
    # Update JSON file if it exists
    updated_in_file = False
    file_path = get_transcript_file_path(meeting_name)
    if file_path.exists():
        try:
            transcript_data = {
                "meeting_name": meeting_name,
                "transcripts": [
                    {"speaker": speaker, "text": text, "is_final": True}
                    for speaker, text in transcript_entries
                ],
                "total_entries": len(transcript_entries),
            }
            
            # Add user_id to metadata
            if user_id:
                transcript_data["user_id"] = user_id
            
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(transcript_data, f, indent=2, ensure_ascii=False)
            
            updated_in_file = True
            logger.info(f"✅ Updated transcript file: {file_path}")
        except Exception as e:
            logger.warning(f"⚠️  Error updating JSON file: {e}")
    
    if updated_in_vector_db or updated_in_file:
        return {
            "status": "ok",
            "message": "Transcript updated successfully",
            "meeting_name": meeting_name,
            "total_entries": len(transcript_entries),
            "updated_in_vector_db": updated_in_vector_db,
            "updated_in_file": updated_in_file,
            "transcripts": [
                {"speaker": speaker, "text": text, "is_final": True}
                for speaker, text in transcript_entries
            ]
        }
    else:
        raise HTTPException(
            status_code=500,
            detail="Failed to update transcript in both vector DB and file"
        )


@app.post("/token")
async def generate_token(request: TokenRequest, current_user = Depends(get_current_user)):
    """Generate a LiveKit access token for a room"""
    try:
        from livekit import api
        from config import LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, validate_livekit_config

        # Validate configuration
        try:
            validate_livekit_config()
        except ValueError as e:
            raise HTTPException(
                status_code=500,
                detail=f"LiveKit API credentials not configured: {str(e)}. Please create a .env.local file in the backend directory with LIVEKIT_API_KEY and LIVEKIT_API_SECRET. See README.md for setup instructions.",
            )

        identity = request.identity
        if not identity:
            import uuid

            identity = f"user-{uuid.uuid4().hex[:8]}"

        token = (
            api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
            .with_identity(identity)
            .with_name(identity)
            .with_grants(
                api.VideoGrants(
                    room_join=True,
                    room=request.room_name,
                    can_publish=True,
                    can_subscribe=True,
                )
            )
        )

        # Store room_name -> user_id mapping for later transcript storage
        try:
            from room_user_mapping import store_room_user_mapping
            store_room_user_mapping(request.room_name, current_user.id)
            logger.info(f"Stored room mapping: {request.room_name} -> user_id {current_user.id}")
        except Exception as e:
            logger.warning(f"Failed to store room mapping: {e}")

        return {
            "token": token.to_jwt(),
            "url": LIVEKIT_URL,
            "room_name": request.room_name,
            "identity": identity,
        }
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="LiveKit API package not installed. Install with: pip install livekit-api",
        )
    except Exception as e:
        logger.error(f"Error generating token: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/ws/transcripts")
async def websocket_endpoint(websocket: WebSocket):
    client_host = websocket.client.host if websocket.client else "unknown"

    # Extract token from query string (FastAPI WebSocket doesn't support Query() directly)
    token = None
    if websocket.url.query:
        from urllib.parse import parse_qs
        query_params = parse_qs(websocket.url.query)
        token = query_params.get("token", [None])[0] if query_params.get("token") else None

    # Authenticate WebSocket connection
    if not token:
        logger.warning(f"WebSocket connection rejected from {client_host}: No token provided")
        try:
            await websocket.close(code=1008, reason="Authentication required")
        except Exception:
            pass
        return
    
    # Verify token and extract username
    payload = verify_token(token)
    if not payload:
        logger.warning(f"WebSocket connection rejected from {client_host}: Invalid token")
        try:
            await websocket.close(code=1008, reason="Invalid token")
        except Exception:
            pass
        return
    
    username = payload.get("sub")  # JWT 'sub' field contains username
    if not username:
        logger.warning(f"WebSocket connection rejected from {client_host}: No username in token")
        try:
            await websocket.close(code=1008, reason="Invalid token payload")
        except Exception:
            pass
        return
    
    # Look up user by username to get user_id
    db_gen = get_db()
    try:
        db = next(db_gen)
        user = get_user_by_username(db, username=username)
        if not user:
            logger.warning(f"WebSocket connection rejected from {client_host}: User not found: {username}")
            try:
                await websocket.close(code=1008, reason="User not found")
            except Exception:
                pass
            return
        
        user_id = user.id
    except Exception as e:
        logger.error(f"Failed to look up user for WebSocket connection: {e}")
        try:
            await websocket.close(code=1008, reason="Database error")
        except Exception:
            pass
        return
    finally:
        # Close the database session by exhausting the generator
        try:
            next(db_gen, None)
        except StopIteration:
            pass
    
    try:
        await transcript_manager.connect(websocket, int(user_id))
        logger.info(
            f"WebSocket client connected from {client_host} (user_id={user_id}). Total connections: {len(transcript_manager.connections)}"
        )
    except Exception as e:
        logger.error(f"Failed to accept WebSocket connection from {client_host}: {e}")
        try:
            await websocket.close(code=1000, reason="Server error")
        except Exception:
            pass
        return

    try:
        # Keep connection alive and handle incoming messages
        while True:
            try:
                data = await websocket.receive_text()
                try:
                    message = json.loads(data)
                    logger.info(
                        f"📨 Received WebSocket message from {client_host}: {message}"
                    )
                    message_type = message.get("type")

                    if message_type == "request_transcript":
                        # Client is requesting the complete transcript
                        room_name = message.get("room_name", "Meeting")
                        logger.info(
                            f"🎯 Client {client_host} (user_id={user_id}) requested transcript for room: {room_name}"
                        )

                        # Validate user ownership of the transcript
                        file_user_id = get_user_id_for_room(room_name)
                        if file_user_id and file_user_id != user_id:
                            logger.warning(
                                f"⚠️  User {user_id} attempted to access transcript for room {room_name} owned by user {file_user_id}"
                            )
                            await websocket.send_json({
                                "type": "error",
                                "message": "Access denied: This transcript belongs to another user"
                            })
                            continue

                        transcript_found = False
                        
                        # First, try to get from vector database
                        try:
                            from vector_db.vector_store import get_redis_client
                            import json as json_module
                            
                            client = get_redis_client()
                            keys = client.keys("transcript:*")
                            
                            # Search for matching transcript by meeting_name and user_id
                            for key in keys:
                                data = client.hgetall(key)
                                stored_meeting_name = data.get(b'meeting_name')
                                stored_user_id = data.get(b'user_id')
                                
                                if stored_meeting_name and stored_user_id:
                                    stored_meeting_name_str = stored_meeting_name.decode('utf-8')
                                    stored_user_id_str = int(stored_user_id.decode('utf-8'))
                                    
                                    if stored_meeting_name_str == room_name and stored_user_id_str == user_id:
                                        # Found in vector DB - parse transcript_text back to transcript entries
                                        transcript_text = data.get(b'transcript_text', b'').decode('utf-8')
                                        
                                        # Parse transcript_text back to individual entries
                                        # Format: "Speaker 1: text\nSpeaker 2: text"
                                        transcript_entries = []
                                        for line in transcript_text.split('\n'):
                                            if ':' in line:
                                                parts = line.split(':', 1)
                                                if len(parts) == 2:
                                                    speaker = parts[0].strip()
                                                    text = parts[1].strip()
                                                    if text:
                                                        transcript_entries.append({
                                                            "speaker": speaker,
                                                            "text": text,
                                                            "is_final": True
                                                        })
                                        
                                        message_to_send = {
                                            "type": "complete_transcript",
                                            "meeting_title": room_name,
                                            "transcripts": transcript_entries,
                                        }
                                        
                                        try:
                                            await websocket.send_json(message_to_send)
                                            logger.info(
                                                f"✅ Sent transcript from vector DB to {client_host} (user_id={user_id}, {len(transcript_entries)} entries)"
                                            )
                                            transcript_found = True
                                        except Exception as e:
                                            logger.error(f"Error sending transcript to client: {e}")
                                            transcript_manager.disconnect(websocket)
                                        break
                        except Exception as e:
                            logger.warning(f"Error fetching from vector DB, trying file: {e}")
                        
                        # If not found in vector DB, try to load from file
                        if not transcript_found:
                            transcript_data = load_transcript_from_file(room_name)
                            if transcript_data:
                                # Verify ownership from file metadata if available
                                file_user_id_from_data = transcript_data.get("user_id")
                                if file_user_id_from_data and int(file_user_id_from_data) != user_id:
                                    logger.warning(
                                        f"⚠️  User {user_id} attempted to access transcript file for room {room_name} owned by user {file_user_id_from_data}"
                                    )
                                    await websocket.send_json({
                                        "type": "error",
                                        "message": "Access denied: This transcript belongs to another user"
                                    })
                                    continue
                                
                                # Send from file to this user only
                                logger.info(
                                    f"📖 Loaded transcript from file: {room_name}.json ({transcript_data.get('total_entries', 0)} entries)"
                                )
                                message_to_send = {
                                    "type": "complete_transcript",
                                    "meeting_title": transcript_data.get(
                                        "meeting_name", room_name
                                    ),
                                    "transcripts": transcript_data.get("transcripts", []),
                                }

                                # Send only to this specific connection (user)
                                try:
                                    await websocket.send_json(message_to_send)
                                    logger.info(
                                        f"✅ Sent transcript from file to {client_host} (user_id={user_id})"
                                    )
                                    transcript_found = True
                                except Exception as e:
                                    logger.error(
                                        f"Error sending transcript to client: {e}"
                                    )
                                    transcript_manager.disconnect(websocket)
                        
                        # If still not found, fall back to memory (user-specific)
                        if not transcript_found:
                            user_transcripts = transcript_manager.user_transcripts.get(user_id, [])
                            logger.info(
                                f"📊 Current transcripts in manager for user_id={user_id}: {len(user_transcripts)}"
                            )
                            if user_transcripts:
                                logger.info(
                                    f"📝 Sending {len(user_transcripts)} transcripts from memory to {client_host} (user_id={user_id})"
                                )
                                message_to_send = {
                                    "type": "complete_transcript",
                                    "meeting_title": room_name,
                                    "transcripts": [
                                        {"speaker": sp, "text": txt, "is_final": is_final}
                                        for sp, txt, is_final in user_transcripts
                                    ],
                                }
                                try:
                                    await websocket.send_json(message_to_send)
                                    logger.info(
                                        f"✅ Sent transcript from memory to {client_host} (user_id={user_id})"
                                    )
                                except Exception as e:
                                    logger.error(f"Error sending transcript to client: {e}")
                                    transcript_manager.disconnect(websocket)
                            else:
                                logger.warning(
                                    f"⚠️  No transcripts available for user_id={user_id} in vector DB, file, or memory."
                                )
                                await websocket.send_json({
                                    "type": "complete_transcript",
                                    "meeting_title": room_name,
                                    "transcripts": [],
                                })

                    elif message_type == "watch_transcript":
                        # Client wants to watch a transcript file for real-time updates
                        meeting_name = message.get("meeting_name") or message.get(
                            "room_name"
                        )
                        if meeting_name:
                            # Validate user ownership before allowing watch
                            file_user_id = get_user_id_for_room(meeting_name)
                            if file_user_id and file_user_id != user_id:
                                logger.warning(
                                    f"⚠️  User {user_id} attempted to watch transcript for room {meeting_name} owned by user {file_user_id}"
                                )
                                await websocket.send_json({
                                    "type": "error",
                                    "message": "Access denied: This transcript belongs to another user"
                                })
                                continue
                            
                            logger.info(
                                f"👁️  Client {client_host} (user_id={user_id}) wants to watch transcript: {meeting_name}"
                            )
                            transcript_manager.file_watcher.add_watcher(
                                meeting_name, websocket
                            )

                            # Also send current transcript if file exists (and user owns it)
                            transcript_data = load_transcript_from_file(meeting_name)
                            if transcript_data:
                                # Verify ownership from file metadata if available
                                file_user_id_from_data = transcript_data.get("user_id")
                                if file_user_id_from_data and int(file_user_id_from_data) != user_id:
                                    logger.warning(
                                        f"⚠️  User {user_id} attempted to watch transcript file for room {meeting_name} owned by user {file_user_id_from_data}"
                                    )
                                    await websocket.send_json({
                                        "type": "error",
                                        "message": "Access denied: This transcript belongs to another user"
                                    })
                                    continue
                                
                                message_to_send = {
                                    "type": "complete_transcript",
                                    "meeting_title": transcript_data.get(
                                        "meeting_name", meeting_name
                                    ),
                                    "transcripts": transcript_data.get(
                                        "transcripts", []
                                    ),
                                }
                                try:
                                    await websocket.send_json(message_to_send)
                                    logger.info(
                                        f"✅ Sent initial transcript to watcher: {meeting_name} (user_id={user_id})"
                                    )
                                except Exception as e:
                                    logger.error(
                                        f"Error sending initial transcript: {e}"
                                    )
                        else:
                            logger.warning(
                                "⚠️  watch_transcript message missing meeting_name"
                            )

                    elif message_type == "unwatch_transcript":
                        # Client wants to stop watching a transcript file
                        meeting_name = message.get("meeting_name") or message.get(
                            "room_name"
                        )
                        if meeting_name:
                            logger.info(
                                f"👁️  Client {client_host} wants to stop watching transcript: {meeting_name}"
                            )
                            transcript_manager.file_watcher.remove_watcher(
                                meeting_name, websocket
                            )
                        else:
                            logger.warning(
                                "⚠️  unwatch_transcript message missing meeting_name"
                            )
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
        logger.info(
            f"WebSocket client {client_host} disconnected. Total connections: {len(transcript_manager.connections)}"
        )


def get_transcript_manager() -> TranscriptManager:
    """Get the global transcript manager instance"""
    return transcript_manager
