"""Room to user mapping utility for associating room names with user IDs"""

import os
import logging
from typing import Optional
from dotenv import load_dotenv
import redis

load_dotenv(".env.local")

logger = logging.getLogger(__name__)

# Redis configuration (reuse same Redis instance)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Redis key prefix for room mappings
ROOM_MAPPING_PREFIX = "room_user:"

# Global Redis client
_redis_client: Optional[redis.Redis] = None


def get_redis_client() -> Optional[redis.Redis]:
    """Get or create Redis client for room mappings"""
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
            # Test connection
            _redis_client.ping()
            logger.debug(f"Connected to Redis for room mappings at {REDIS_URL}")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis for room mappings: {e}")
            logger.warning("Room mappings will not persist across server restarts")
            # Return None if Redis is unavailable - we'll use in-memory fallback
            return None
    return _redis_client


# In-memory fallback dictionary
_in_memory_mappings: dict[str, int] = {}


def store_room_user_mapping(room_name: str, user_id: int) -> bool:
    """
    Store mapping of room_name to user_id
    
    Args:
        room_name: Name of the room/meeting
        user_id: ID of the user who owns the room
    
    Returns:
        True if successful, False otherwise
    """
    try:
        client = get_redis_client()
        if client:
            # Store in Redis
            key = f"{ROOM_MAPPING_PREFIX}{room_name}"
            client.set(key, str(user_id))
            logger.debug(f"Stored room mapping in Redis: {room_name} -> {user_id}")
        else:
            # Fallback to in-memory
            _in_memory_mappings[room_name] = user_id
            logger.debug(f"Stored room mapping in memory: {room_name} -> {user_id}")
        return True
    except Exception as e:
        logger.warning(f"Failed to store room mapping: {e}, using in-memory fallback")
        _in_memory_mappings[room_name] = user_id
        return True


def get_user_id_for_room(room_name: str) -> Optional[int]:
    """
    Get user_id for a given room_name
    
    Args:
        room_name: Name of the room/meeting
    
    Returns:
        user_id if found, None otherwise
    """
    try:
        client = get_redis_client()
        if client:
            # Try Redis first
            key = f"{ROOM_MAPPING_PREFIX}{room_name}"
            user_id_str = client.get(key)
            if user_id_str:
                user_id = int(user_id_str)
                logger.debug(f"Retrieved room mapping from Redis: {room_name} -> {user_id}")
                return user_id
        
        # Fallback to in-memory
        if room_name in _in_memory_mappings:
            user_id = _in_memory_mappings[room_name]
            logger.debug(f"Retrieved room mapping from memory: {room_name} -> {user_id}")
            return user_id
        
        logger.warning(f"No user mapping found for room: {room_name}")
        return None
    except Exception as e:
        logger.warning(f"Failed to get room mapping: {e}")
        # Try in-memory fallback
        return _in_memory_mappings.get(room_name)


def delete_room_mapping(room_name: str) -> bool:
    """
    Delete room mapping (optional cleanup)
    
    Args:
        room_name: Name of the room/meeting
    
    Returns:
        True if successful, False otherwise
    """
    try:
        client = get_redis_client()
        if client:
            key = f"{ROOM_MAPPING_PREFIX}{room_name}"
            client.delete(key)
        
        # Also remove from in-memory
        if room_name in _in_memory_mappings:
            del _in_memory_mappings[room_name]
        
        return True
    except Exception as e:
        logger.warning(f"Failed to delete room mapping: {e}")
        return False

