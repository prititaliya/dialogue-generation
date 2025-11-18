#!/usr/bin/env python3
"""
Redis setup script - checks Redis connection and creates vector index
"""

import os
import sys
import subprocess
import time
from dotenv import load_dotenv

load_dotenv(".env.local")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

def check_redis_running():
    """Check if Redis is running by trying to connect"""
    try:
        import redis
        client = redis.from_url(REDIS_URL, socket_connect_timeout=2)
        client.ping()
        return True, None
    except ImportError:
        return False, "redis package not installed. Run: pip install redis"
    except redis.ConnectionError:
        return False, "Redis server is not running"
    except Exception as e:
        return False, f"Error connecting to Redis: {e}"

def start_redis_server():
    """Try to start Redis server"""
    print("Attempting to start Redis server...")
    
    # Try different methods to start Redis
    redis_commands = [
        ["redis-server"],
        ["brew", "services", "start", "redis"],
        ["redis-stack-server"],
    ]
    
    for cmd in redis_commands:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                print(f"✅ Started Redis with: {' '.join(cmd)}")
                # Wait a bit for Redis to start
                time.sleep(2)
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
            continue
    
    return False

def create_vector_index():
    """Create the vector index in Redis"""
    try:
        from vector_db.vector_store import init_vector_index, get_redis_client
        
        # Test connection
        client = get_redis_client()
        client.ping()
        
        # Create index
        if init_vector_index():
            print("✅ Vector index created/verified successfully")
            return True
        else:
            print("⚠️  Vector index creation failed")
            return False
    except ImportError as e:
        print(f"❌ Cannot import vector_db module: {e}")
        print("   Make sure redis and sentence-transformers are installed:")
        print("   pip install redis sentence-transformers")
        return False
    except Exception as e:
        print(f"❌ Error creating vector index: {e}")
        return False

def main():
    print("=" * 60)
    print("Redis Vector Database Setup")
    print("=" * 60)
    print()
    
    # Check if Redis is running
    is_running, error = check_redis_running()
    
    if is_running:
        print("✅ Redis server is running")
    else:
        print(f"❌ Redis server is not running: {error}")
        print()
        print("Attempting to start Redis...")
        
        if not start_redis_server():
            print()
            print("⚠️  Could not start Redis automatically.")
            print()
            print("Please start Redis manually:")
            print("  macOS (Homebrew):")
            print("    brew services start redis")
            print("    # OR")
            print("    redis-server")
            print()
            print("  Docker:")
            print("    docker run -d --name redis-stack -p 6379:6379 redis/redis-stack:latest")
            print()
            print("  Linux:")
            print("    sudo systemctl start redis")
            print("    # OR")
            print("    redis-server")
            print()
            print("After starting Redis, run this script again.")
            sys.exit(1)
        
        # Check again after attempting to start
        is_running, error = check_redis_running()
        if not is_running:
            print(f"❌ Redis still not running: {error}")
            sys.exit(1)
        print("✅ Redis server started successfully")
    
    print()
    print("Creating vector index...")
    
    # Create vector index
    if create_vector_index():
        print()
        print("=" * 60)
        print("✅ Redis setup completed successfully!")
        print("=" * 60)
        print()
        print("Next steps:")
        print("1. Run the API server: python start_server.py")
        print("2. Transcripts will be stored in vector database when recording stops")
        print("=" * 60)
        sys.exit(0)
    else:
        print()
        print("=" * 60)
        print("⚠️  Redis setup completed but vector index creation had issues")
        print("=" * 60)
        print()
        print("The server will still work, but transcripts will be stored in JSON files only.")
        print("Check the error messages above for details.")
        print("=" * 60)
        sys.exit(1)

if __name__ == "__main__":
    main()

