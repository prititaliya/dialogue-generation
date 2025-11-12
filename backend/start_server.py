"""
Startup script to run both the FastAPI server and LiveKit agent
"""

import uvicorn
import threading
import time
import sys
import os


def check_database():
    """Check if database setup is needed"""
    try:
        from database.database import engine
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        error_msg = str(e).lower()
        if "does not exist" in error_msg or "database" in error_msg:
            print("⚠️  Database not found. Running setup...")
            try:
                import subprocess
                result = subprocess.run(
                    [sys.executable, "setup_database.py"],
                    cwd=os.path.dirname(__file__),
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    print("✅ Database setup completed!")
                    return True
                else:
                    print("❌ Database setup failed:")
                    print(result.stdout)
                    print(result.stderr)
                    print("\n💡 You can manually run: python setup_database.py")
                    return False
            except Exception as setup_error:
                print(f"❌ Error running database setup: {setup_error}")
                print("💡 You can manually run: python setup_database.py")
                return False
        else:
            print(f"⚠️  Database connection issue: {e}")
            print("💡 Make sure PostgreSQL is running and check your DATABASE_URL in .env.local")
            return False


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
    # Check database before starting
    if not check_database():
        print("\n⚠️  Starting server anyway, but authentication may not work...")
        print("   Fix the database issue and restart the server.\n")
    
    # Start API server in a separate thread
    api_thread = threading.Thread(target=run_api_server, daemon=True)
    api_thread.start()
    print("🚀 API server started on http://localhost:8000")
    print("📡 WebSocket endpoint: ws://localhost:8000/ws/transcripts")
    print("📚 API docs: http://localhost:8000/docs")
    print("💡 Note: Start the LiveKit agent separately with: python main.py dev")
    print("   Or use: python main.py start (for production)")

    # Keep the main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
