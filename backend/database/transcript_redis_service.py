"""
Redis service for storing and managing active transcripts
Mirrors the JSON file operations but uses Redis for storage
"""

import os
import json
import logging
from typing import Optional, Dict, List, Tuple
from dotenv import load_dotenv
import redis

load_dotenv(".env.local")

logger = logging.getLogger(__name__)

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Redis key prefixes
ACTIVE_TRANSCRIPT_PREFIX = "active_transcript:"
TRANSCRIPT_UPDATE_CHANNEL_PREFIX = "transcript_updates:"

# Global Redis client
_redis_client: Optional[redis.Redis] = None


def get_redis_client() -> Optional[redis.Redis]:
    """Get or create Redis client for active transcripts"""
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
            _redis_client.ping()
            logger.info(f"✅ Connected to Redis for active transcripts at {REDIS_URL}")
        except Exception as e:
            logger.warning(f"⚠️  Failed to connect to Redis for active transcripts: {e}")
            # Return None if Redis is unavailable
            return None
    return _redis_client


def get_active_transcript_key(meeting_name: str) -> str:
    """Get Redis key for an active transcript"""
    # Sanitize meeting name to be Redis key-safe
    safe_name = "".join(
        c for c in meeting_name if c.isalnum() or c in ("-", "_", " ")
    ).strip().replace(" ", "_")
    return f"{ACTIVE_TRANSCRIPT_PREFIX}{safe_name}"


def get_transcript_update_channel(meeting_name: str) -> str:
    """Get Redis pub/sub channel for transcript updates"""
    safe_name = "".join(
        c for c in meeting_name if c.isalnum() or c in ("-", "_", " ")
    ).strip().replace(" ", "_")
    return f"{TRANSCRIPT_UPDATE_CHANNEL_PREFIX}{safe_name}"


def save_transcript_to_redis(
    meeting_name: str, transcripts: List[Tuple[str, str]]
) -> bool:
    """
    Save transcripts to Redis (equivalent to save_transcript_to_file)
    
    Args:
        meeting_name: Name of the meeting/room
        transcripts: List of (speaker, text) tuples
        
    Returns:
        True if successful, False otherwise
    """
    client = get_redis_client()
    if not client:
        logger.error("❌ Redis client not available for saving transcript")
        return False
    
    try:
        key = get_active_transcript_key(meeting_name)
        transcript_data = {
            "meeting_name": meeting_name,
            "transcripts": [
                {"speaker": speaker, "text": text, "is_final": True}
                for speaker, text in transcripts
            ],
            "total_entries": len(transcripts),
        }
        
        # Store as JSON string in Redis
        client.set(key, json.dumps(transcript_data, ensure_ascii=False))
        
        # Publish update notification
        channel = get_transcript_update_channel(meeting_name)
        client.publish(channel, json.dumps({
            "type": "full_update",
            "meeting_name": meeting_name,
            "total_entries": len(transcripts)
        }))
        
        logger.info(
            f"💾 Saved transcript to Redis: {key} ({len(transcripts)} entries)"
        )
        return True
    except Exception as e:
        logger.error(f"❌ Failed to save transcript to Redis: {e}")
        return False


def load_transcript_from_redis(meeting_name: str) -> Optional[Dict]:
    """
    Load transcript from Redis (equivalent to load_transcript_from_file)
    
    Args:
        meeting_name: Name of the meeting/room
        
    Returns:
        Transcript data dict or None if not found
    """
    client = get_redis_client()
    if not client:
        logger.warning("⚠️  Redis client not available for loading transcript")
        return None
    
    try:
        key = get_active_transcript_key(meeting_name)
        data_str = client.get(key)
        
        if not data_str:
            logger.debug(f"📄 Transcript not found in Redis: {key}")
            return None
        
        data = json.loads(data_str)
        logger.info(
            f"📖 Loaded transcript from Redis: {key} ({data.get('total_entries', 0)} entries)"
        )
        return data
    except json.JSONDecodeError as e:
        logger.error(f"❌ Error decoding transcript data from Redis: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Error loading transcript from Redis: {e}")
        return None


def update_transcript_incremental_redis(
    meeting_name: str,
    speaker: str,
    text: str,
    is_final: bool = False,
    broadcast: bool = True,
) -> bool:
    """
    Incrementally update transcript in Redis for each word/speech event.
    Equivalent to update_transcript_incremental but uses Redis.
    
    - For interim events: Update the last entry if same speaker, or create new entry
    - For final events: Mark current entry as final
    
    Args:
        meeting_name: Name of the meeting/room
        speaker: Speaker identifier
        text: Transcript text
        is_final: Whether this is a final transcript or interim
        broadcast: Whether to publish update notification
        
    Returns:
        True if successful, False otherwise
    """
    client = get_redis_client()
    if not client:
        logger.error("❌ Redis client not available for updating transcript")
        return False
    
    try:
        key = get_active_transcript_key(meeting_name)
        
        # Load existing data or create new structure
        data_str = client.get(key)
        if data_str:
            data = json.loads(data_str)
        else:
            data = {"meeting_name": meeting_name, "transcripts": [], "total_entries": 0}
        
        transcripts = data.get("transcripts", [])
        
        if is_final:
            # Final event: Mark the last entry as final if it matches this speaker
            text_stripped = text.strip()
            if not text_stripped:
                # Skip empty text
                return True
            
            if transcripts:
                last_entry = transcripts[-1]
                last_text = last_entry.get("text", "").strip()
                
                if last_entry.get("speaker") == speaker and not last_entry.get(
                    "is_final", False
                ):
                    # Update existing interim entry to final
                    if last_text != text_stripped:
                        transcripts[-1] = {
                            "speaker": speaker,
                            "text": text_stripped,
                            "is_final": True,
                        }
                elif last_entry.get("speaker") == speaker and last_entry.get(
                    "is_final", False
                ):
                    # Same speaker, final entry - check if text is an extension or duplicate
                    if last_text == text_stripped:
                        # Exact duplicate - skip adding
                        logger.debug(
                            f"⏭️  Skipping duplicate final transcript: {speaker} - {text_stripped[:30]}..."
                        )
                        return True
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
                        # Check if this exact text already exists in recent entries
                        is_duplicate = False
                        for entry in transcripts[-3:]:
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
                            transcripts.append(
                                {
                                    "speaker": speaker,
                                    "text": text_stripped,
                                    "is_final": True,
                                }
                            )
                        else:
                            return True
                else:
                    # Different speaker - check if this exact text already exists in recent entries
                    is_duplicate = False
                    for entry in transcripts[-3:]:
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
                        transcripts.append(
                            {
                                "speaker": speaker,
                                "text": text_stripped,
                                "is_final": True,
                            }
                        )
                    else:
                        return True
            else:
                # No existing transcripts, create first final entry
                transcripts.append(
                    {"speaker": speaker, "text": text_stripped, "is_final": True}
                )
        else:
            # Interim event: Update last entry if same speaker, or create new interim entry
            if transcripts:
                last_entry = transcripts[-1]
                if last_entry.get("speaker") == speaker and not last_entry.get(
                    "is_final", False
                ):
                    # Update existing interim entry
                    transcripts[-1] = {
                        "speaker": speaker,
                        "text": text.strip(),
                        "is_final": False,
                    }
                elif last_entry.get("speaker") == speaker and last_entry.get(
                    "is_final", False
                ):
                    # Same speaker but last entry was final, create new interim entry
                    transcripts.append(
                        {"speaker": speaker, "text": text.strip(), "is_final": False}
                    )
                else:
                    # Different speaker, create new interim entry
                    transcripts.append(
                        {"speaker": speaker, "text": text.strip(), "is_final": False}
                    )
            else:
                # No existing transcripts, create first interim entry
                transcripts.append(
                    {"speaker": speaker, "text": text.strip(), "is_final": False}
                )
        
        # Update data structure
        data["transcripts"] = transcripts
        data["total_entries"] = len(
            [t for t in transcripts if t.get("is_final", False)]
        )
        
        # Save back to Redis
        client.set(key, json.dumps(data, ensure_ascii=False))
        
        logger.debug(
            f"💾 Incrementally updated transcript in Redis: {speaker} - {text[:30]}... (final={is_final})"
        )
        
        # Publish update notification if broadcast is enabled
        if broadcast:
            channel = get_transcript_update_channel(meeting_name)
            update_message = {
                "type": "incremental_update",
                "meeting_name": meeting_name,
                "speaker": speaker,
                "text": text.strip(),
                "is_final": is_final,
                "total_entries": data["total_entries"],
            }
            client.publish(channel, json.dumps(update_message))
        
        return True
        
    except json.JSONDecodeError as e:
        logger.error(f"❌ Error decoding transcript data in Redis: {e}")
        return False
    except Exception as e:
        logger.error(
            f"❌ Failed to incrementally update transcript in Redis: {e}"
        )
        return False


def delete_transcript_from_redis(meeting_name: str) -> bool:
    """
    Delete an active transcript from Redis
    
    Args:
        meeting_name: Name of the meeting/room
        
    Returns:
        True if successful, False otherwise
    """
    client = get_redis_client()
    if not client:
        return False
    
    try:
        key = get_active_transcript_key(meeting_name)
        deleted = client.delete(key)
        if deleted:
            logger.info(f"🗑️  Deleted transcript from Redis: {key}")
        return deleted > 0
    except Exception as e:
        logger.error(f"❌ Failed to delete transcript from Redis: {e}")
        return False


def list_active_transcripts() -> List[str]:
    """
    List all active transcript meeting names from Redis
    
    Returns:
        List of meeting names
    """
    client = get_redis_client()
    if not client:
        return []
    
    try:
        pattern = f"{ACTIVE_TRANSCRIPT_PREFIX}*"
        keys = client.keys(pattern)
        # Extract meeting names from keys
        meeting_names = []
        prefix_len = len(ACTIVE_TRANSCRIPT_PREFIX)
        for key in keys:
            meeting_name = key[prefix_len:]
            meeting_names.append(meeting_name)
        return meeting_names
    except Exception as e:
        logger.error(f"❌ Failed to list active transcripts from Redis: {e}")
        return []

