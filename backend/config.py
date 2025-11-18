"""
Centralized configuration for LiveKit and other services.
All LiveKit-related configuration should be imported from here.
"""
import os
from dotenv import load_dotenv

load_dotenv(".env.local")

# LiveKit Configuration
LIVEKIT_URL = os.getenv("LIVEKIT_URL", "wss://mirai-mqlay2oc.livekit.cloud")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")

def get_livekit_config():
    """
    Get LiveKit configuration as a dictionary.
    Returns all LiveKit-related settings.
    """
    return {
        "url": LIVEKIT_URL,
        "api_key": LIVEKIT_API_KEY,
        "api_secret": LIVEKIT_API_SECRET,
    }

def validate_livekit_config():
    """
    Validate that all required LiveKit configuration is present.
    Raises ValueError if any required config is missing.
    """
    if not LIVEKIT_API_KEY:
        raise ValueError("LIVEKIT_API_KEY is not set in .env.local")
    if not LIVEKIT_API_SECRET:
        raise ValueError("LIVEKIT_API_SECRET is not set in .env.local")
    return True

