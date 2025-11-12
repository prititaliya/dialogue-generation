"""
Startup script to run both the FastAPI server and LiveKit agent
"""

import uvicorn
import threading
import time


def run_api_server():
    """Run the FastAPI server in a separate thread"""
    from api_server import app

    # Explicitly enable WebSocket support
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        ws="auto",  # Enable WebSocket support
    )


if __name__ == "__main__":
    # Start API server in a separate thread
    api_thread = threading.Thread(target=run_api_server, daemon=True)
    api_thread.start()
    print("🚀 API server started on http://localhost:8000")
    print("📡 WebSocket endpoint: ws://localhost:8000/ws/transcripts")
    print("💡 Note: Start the LiveKit agent separately with: python main.py dev")
    print("   Or use: python main.py start (for production)")

    # Keep the main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
