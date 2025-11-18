"""Vector database service for storing transcripts with embeddings using Redis Stack"""

import os
import json
import logging
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv
import redis
from sentence_transformers import SentenceTransformer

load_dotenv(".env.local")

logger = logging.getLogger(__name__)

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
REDIS_INDEX_NAME = os.getenv("REDIS_INDEX_NAME", "transcripts:index")

# Embedding model configuration
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384  # Dimension for all-MiniLM-L6-v2 model

# Global variables
_redis_client: Optional[redis.Redis] = None
_embedding_model: Optional[SentenceTransformer] = None


def get_redis_client() -> redis.Redis:
    """Get or create Redis client"""
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = redis.from_url(REDIS_URL, decode_responses=False)
            # Test connection
            _redis_client.ping()
            logger.info(f"✅ Connected to Redis at {REDIS_URL}")
        except Exception as e:
            logger.error(f"❌ Failed to connect to Redis: {e}")
            raise
    return _redis_client


def get_embedding_model() -> SentenceTransformer:
    """Get or load embedding model"""
    global _embedding_model
    if _embedding_model is None:
        try:
            logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
            _embedding_model = SentenceTransformer(EMBEDDING_MODEL)
            logger.info("✅ Embedding model loaded successfully")
        except ImportError as e:
            error_msg = str(e)
            if "tensorflow" in error_msg.lower():
                logger.error(
                    f"❌ TensorFlow import failed. This is often due to incompatible dependencies. "
                    f"Try: pip install --upgrade tensorflow or use a different Python environment."
                )
            logger.error(f"❌ Failed to load embedding model: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Failed to load embedding model: {e}")
            raise
    return _embedding_model


def get_embedding(text: str) -> List[float]:
    """Generate embedding for text using sentence-transformers"""
    model = get_embedding_model()
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()


def init_vector_index() -> bool:
    """Initialize Redis - check if RediSearch is available, otherwise use regular Redis"""
    try:
        client = get_redis_client()
        
        # Check if RediSearch (FT commands) is available
        try:
            # Try to use FT.INFO to check if RediSearch is available
            client.execute_command("FT.INFO", REDIS_INDEX_NAME)
            logger.info(f"✅ RediSearch available - vector index '{REDIS_INDEX_NAME}' exists")
            return True
        except redis.exceptions.ResponseError as e:
            error_msg = str(e).lower()
            if "no such index" in error_msg:
                # RediSearch is available but index doesn't exist - create it
                try:
                    client.execute_command(
                        "FT.CREATE", REDIS_INDEX_NAME,
                        "ON", "HASH",
                        "PREFIX", "1", "transcript:",
                        "SCHEMA",
                        "embedding", "VECTOR", "HNSW", "6",
                            "TYPE", "FLOAT32",
                            "DIM", str(EMBEDDING_DIMENSION),
                            "DISTANCE_METRIC", "COSINE",
                        "user_id", "TAG",
                        "meeting_id", "TEXT",
                        "meeting_name", "TEXT",
                        "timestamp", "NUMERIC",
                        "transcript_text", "TEXT",
                        "speakers", "TEXT"
                    )
                    logger.info(f"✅ Created vector index '{REDIS_INDEX_NAME}' with RediSearch")
                    return True
                except redis.exceptions.ResponseError as create_error:
                    if "index already exists" in str(create_error).lower():
                        logger.info(f"✅ Vector index '{REDIS_INDEX_NAME}' already exists")
                        return True
                    else:
                        raise
            elif "unknown command" in error_msg or "ft.info" in error_msg:
                # RediSearch not available - use regular Redis (no vector search, but persistence works)
                logger.warning("⚠️  RediSearch not available - using regular Redis for storage")
                logger.info("✅ Redis connection verified - transcripts will be stored as hashes (no vector search)")
                return True
            else:
                raise
                
    except Exception as e:
        logger.error(f"❌ Failed to initialize Redis: {e}")
        return False


def store_transcript(
    user_id: int,
    meeting_name: str,
    transcript_text: str,
    speakers: List[str],
    timestamp: Optional[float] = None,
    meeting_id: Optional[str] = None,
) -> Optional[str]:
    """
    Store transcript in Redis vector database
    
    Args:
        user_id: User ID who owns the transcript
        meeting_name: Name of the meeting/room
        transcript_text: Full transcript text (combined from all entries)
        speakers: List of unique speaker names
        timestamp: Unix timestamp (defaults to current time)
        meeting_id: Unique meeting ID (defaults to generated UUID)
    
    Returns:
        meeting_id if successful, None if failed
    """
    try:
        client = get_redis_client()
        
        # Generate meeting_id if not provided
        if meeting_id is None:
            meeting_id = str(uuid.uuid4())
        
        # Use current timestamp if not provided
        if timestamp is None:
            timestamp = datetime.now().timestamp()
        
        # Generate embedding
        logger.info(f"Generating embedding for transcript: {meeting_name}")
        embedding = get_embedding(transcript_text)
        
        # Prepare document data
        doc_id = f"transcript:{meeting_id}"
        
        # Convert embedding to binary format for Redis vector field
        import numpy as np
        embedding_array = np.array(embedding, dtype=np.float32)
        embedding_bytes = embedding_array.tobytes()
        
        # Store metadata fields
        doc_data = {
            "user_id": str(user_id),
            "meeting_id": meeting_id,
            "meeting_name": meeting_name,
            "timestamp": str(int(timestamp)),
            "transcript_text": transcript_text,
            "speakers": json.dumps(speakers),
        }
        
        # Store in Redis as hash
        client.hset(doc_id, mapping=doc_data)
        
        # Store vector field separately as binary (required for Redis vector search)
        client.hset(doc_id, "embedding", embedding_bytes)
        
        logger.info(
            f"✅ Stored transcript in vector DB: meeting_id={meeting_id}, "
            f"user_id={user_id}, meeting_name={meeting_name}"
        )
        
        return meeting_id
        
    except Exception as e:
        logger.error(f"❌ Failed to store transcript in vector DB: {e}")
        return None


class VectorStore:
    """Vector store class for managing transcript embeddings"""
    
    def __init__(self):
        self.client = None
        self.model = None
    
    def initialize(self) -> bool:
        """Initialize Redis connection and embedding model"""
        try:
            self.client = get_redis_client()
            self.model = get_embedding_model()
            return True
        except Exception as e:
            logger.error(f"Failed to initialize VectorStore: {e}")
            return False
    
    def store(
        self,
        user_id: int,
        meeting_name: str,
        transcript_text: str,
        speakers: List[str],
        timestamp: Optional[float] = None,
        meeting_id: Optional[str] = None,
    ) -> Optional[str]:
        """Store transcript (wrapper around store_transcript)"""
        return store_transcript(
            user_id=user_id,
            meeting_name=meeting_name,
            transcript_text=transcript_text,
            speakers=speakers,
            timestamp=timestamp,
            meeting_id=meeting_id,
        )

