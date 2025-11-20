# Complete Testing & Running Guide

This guide provides detailed instructions for setting up, running, and testing the Dialogue Generation system.

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [First-Time Setup](#first-time-setup)
3. [Environment Configuration](#environment-configuration)
4. [Running the Application](#running-the-application)
5. [Testing Procedures](#testing-procedures)
6. [Verification Checklist](#verification-checklist)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Software

1. **Python 3.12+**
   ```bash
   python --version  # Should show 3.12 or higher
   ```

2. **Node.js 18+ and npm**
   ```bash
   node --version  # Should show v18 or higher
   npm --version
   ```

3. **PostgreSQL** (for user authentication)
   ```bash
   # macOS
   brew install postgresql
   
   # Linux
   sudo apt-get install postgresql
   ```

4. **Redis** (for transcript storage)
   ```bash
   # macOS
   brew install redis
   
   # Linux
   sudo apt-get install redis-server
   ```

5. **Git** (for cloning/updating the repository)

### Required API Keys

You'll need API keys for:
- **Speechmatics** - For speech-to-text and speaker diarization
- **OpenAI** - For speaker name extraction
- **LiveKit** - For WebRTC audio streaming

---

## First-Time Setup

### Step 1: Clone/Verify Repository

```bash
cd /Users/krish/Desktop/ME/Code/TrascriptGeneration/dialogue-generation
```

### Step 2: Backend Setup

```bash
cd backend

# Install Python dependencies
# Option 1: Using uv (recommended)
uv sync

# Option 2: Using pip
pip install -r requirements.txt

# Or create a virtual environment first (recommended)
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Step 3: Frontend Setup

```bash
cd frontend

# Install Node.js dependencies
npm install
```

### Step 4: Database Setup

```bash
# Start PostgreSQL (if not running)
# macOS
brew services start postgresql

# Linux
sudo systemctl start postgresql

# Setup database schema
cd backend
python setup_database.py
```

### Step 5: Redis Setup

```bash
# Start Redis (if not running)
# macOS
brew services start redis

# Or manually
redis-server

# Setup Redis indexes
cd backend
python setup_redis.py
```

---

## Environment Configuration

### Backend Environment Variables

Create `backend/.env.local` file:

```bash
cd backend
touch .env.local
```

Add the following content (replace with your actual keys):

```env
# Database
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/dialogue_db

# Redis
REDIS_URL=redis://localhost:6379
REDIS_INDEX_NAME=transcripts:index

# LiveKit Configuration
LIVEKIT_URL=wss://your-livekit-url.livekit.cloud
LIVEKIT_API_KEY=your_livekit_api_key
LIVEKIT_API_SECRET=your_livekit_api_secret

# Speechmatics (for transcription)
SPEECHMATICS_API_KEY=your_speechmatics_api_key

# OpenAI (for speaker name extraction)
OPENAI_API_KEY=your_openai_api_key

# JWT Secret (for authentication)
JWT_SECRET_KEY=your-secret-key-change-in-production-use-random-string
```

**Important:** 
- Replace all placeholder values with your actual API keys
- Keep `.env.local` secure and never commit it to git
- The JWT_SECRET_KEY should be a long random string

### Frontend Environment Variables

Create `frontend/.env` file:

```bash
cd frontend
touch .env
```

Add the following content:

```env
# Backend API URL (WebSocket)
VITE_API_URL=ws://localhost:8000

# LiveKit Server URL
VITE_LIVEKIT_URL=wss://your-livekit-url.livekit.cloud
```

---

## Running the Application

### Method 1: TMUX Startup (Recommended - All in One Window)

The easiest way to start everything with all services visible in one terminal:

```bash
# From project root
./start_tmux.sh
```

This script will:
- ✅ Check and start PostgreSQL & Redis if needed
- ✅ Create a tmux session with 4 panes
- ✅ Start Backend API Server in pane 0 (top-left)
- ✅ Start LiveKit Agent in pane 1 (top-right)
- ✅ Start Frontend in pane 2 (bottom-left)
- ✅ Start Status Monitor in pane 3 (bottom-right)

**Pane Layout:**
```
┌─────────────┬─────────────┐
│ Backend API │ LiveKit     │
│ (port 8000) │ Agent       │
├─────────────┼─────────────┤
│ Frontend    │ Status      │
│ (port 5173) │ Monitor     │
└─────────────┴─────────────┘
```

**TMUX Controls:**
- `Ctrl+B` then `Arrow Keys` - Navigate between panes
- `Ctrl+B` then `D` - Detach (keeps services running)
- `Ctrl+B` then `X` - Close current pane
- `Ctrl+B` then `Z` - Zoom current pane (full screen)
- `Ctrl+B` then `[` - Scroll mode (use arrow keys, `q` to exit)

**To reattach to session:**
```bash
tmux attach -t dialogue-gen
```

**To stop everything:**
```bash
./stop_tmux.sh
```

### Method 2: Automated Startup (Background Processes)

Start everything in the background:

```bash
# From project root
./start_app.sh
```

This script will:
- ✅ Check and start PostgreSQL & Redis if needed
- ✅ Start Backend API Server (port 8000) in background
- ✅ Start LiveKit Agent in background
- ✅ Start Frontend (port 5173) in background

**To stop everything:**
```bash
./stop_app.sh
```

### Method 3: Manual Startup (Step by Step)

If you prefer to run services manually or need to debug:

#### Terminal 1: PostgreSQL (if not running as service)

```bash
# macOS
brew services start postgresql

# Or manually
postgres -D /usr/local/var/postgres
```

#### Terminal 2: Redis (if not running as service)

```bash
redis-server
```

#### Terminal 3: Backend API Server

```bash
cd backend

# Activate virtual environment if using one
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Start the server
python start_server.py
```

**Expected output:**
```
🚀 API server started on http://localhost:8000
📡 WebSocket endpoint: ws://localhost:8000/ws/transcripts
📚 API docs: http://localhost:8000/docs
```

**Keep this terminal open!**

#### Terminal 4: LiveKit Agent

```bash
cd backend

# Activate virtual environment if using one
source .venv/bin/activate

# Start the agent in development mode
python main.py dev
```

**Expected output:**
```
Agent starting in development mode...
Waiting for room connections...
```

**Keep this terminal open!**

#### Terminal 5: Frontend Development Server

```bash
cd frontend
npm run dev
```

**Expected output:**
```
  VITE v7.x.x  ready in xxx ms

  ➜  Local:   http://localhost:5173/
  ➜  Network: use --host to expose
```

**Keep this terminal open!**

---

## Testing Procedures

### 1. Service Status Check

Run the service checker script:

```bash
./check_services.sh
```

**Expected output:**
```
=== Service Status Check ===

1. PostgreSQL:
   ✅ Running on port 5432

2. Redis:
   ✅ Running

3. Backend API (port 8000):
   ✅ Running on port 8000

4. LiveKit Agent:
   ✅ Running (agent process detected)
```

### 2. Backend API Testing

#### Health Check

```bash
curl http://localhost:8000/health
```

**Expected response:**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T12:00:00",
  "services": {
    "database": "connected",
    "redis": "connected"
  }
}
```

#### API Documentation

Open in browser: **http://localhost:8000/docs**

You should see the FastAPI interactive documentation (Swagger UI).

#### Database Health Check

```bash
curl http://localhost:8000/health/db
```

**Expected response:**
```json
{
  "status": "healthy",
  "database": "connected"
}
```

#### Vector DB Health Check

```bash
curl http://localhost:8000/health/vector-db
```

**Expected response:**
```json
{
  "status": "healthy",
  "redis": "connected",
  "index_exists": true
}
```

### 3. WebSocket Testing

#### Test WebSocket Connection

You can test the WebSocket endpoint using a simple Python script:

```bash
cd backend
python -c "
import asyncio
import websockets

async def test():
    uri = 'ws://localhost:8000/ws/transcripts'
    async with websockets.connect(uri) as websocket:
        print('✅ Connected to WebSocket')
        message = await websocket.recv()
        print(f'Received: {message}')

asyncio.run(test())
"
```

**Expected output:**
```
✅ Connected to WebSocket
Received: {"type": "connected", "message": "WebSocket connected"}
```

#### Browser Console Test

1. Open browser DevTools (F12)
2. Go to Console tab
3. Run:

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/transcripts');
ws.onopen = () => console.log('✅ WebSocket connected');
ws.onmessage = (event) => console.log('Received:', event.data);
ws.onerror = (error) => console.error('Error:', error);
```

### 4. Frontend Testing

#### Access the Application

1. Open browser: **http://localhost:5173**

2. **Check Browser Console:**
   - Press F12 to open DevTools
   - Go to Console tab
   - Look for:
     - `✅ WebSocket connected` (success)
     - Any error messages (failure)

3. **Test Authentication:**
   - Try signing up with a new account
   - Try logging in with existing credentials

4. **Test LiveKit Connection:**
   - Enter a room name
   - Enter a LiveKit access token
   - Click "Connect"
   - Check console for connection status

### 5. End-to-End Transcription Test

#### Prerequisites:
- All services running
- Frontend accessible at http://localhost:5173
- LiveKit token generated

#### Steps:

1. **Open Frontend:**
   ```
   http://localhost:5173
   ```

2. **Login/Signup:**
   - Create an account or login
   - You should see the dashboard

3. **Connect to Room:**
   - Enter room name (e.g., "test-room")
   - Enter LiveKit access token
   - Click "Connect"
   - Wait for connection confirmation

4. **Start Sampling Phase:**
   - Speak: "Hi, I'm John" (or your name)
   - System will identify and map speaker names
   - Check console/logs for speaker identification

5. **Begin Transcription:**
   - Say: **"stop sampling"**
   - System will switch to transcription mode
   - Real-time transcripts should appear in the UI

6. **Test Transcription:**
   - Speak naturally
   - Transcripts should appear with speaker labels:
     - `[Final] Speaker Name: your transcript text`
     - `[Interim] Speaker Name: partial text...`

7. **Stop Recording:**
   - Say: **"stop recording"**
   - Session will end
   - Transcripts should be saved

### 6. Database Testing

#### Test User Creation

```bash
# Using psql
psql -U postgres -d dialogue_db

# Check users table
SELECT * FROM users;
```

#### Test Transcript Storage

After a transcription session, check if transcripts are stored:

```bash
# Check Redis
redis-cli
> KEYS transcripts:*
> GET transcripts:meeting_name
```

---

## Verification Checklist

Before testing, verify all services are running:

- [ ] **PostgreSQL** is running (port 5432)
  ```bash
  lsof -ti:5432
  ```

- [ ] **Redis** is running (port 6379)
  ```bash
  redis-cli ping  # Should return: PONG
  ```

- [ ] **Backend API** is running (port 8000)
  ```bash
  curl http://localhost:8000/health
  ```

- [ ] **LiveKit Agent** is running
  ```bash
  ps aux | grep "python.*main.py.*dev"
  ```

- [ ] **Frontend** is running (port 5173)
  ```bash
  curl http://localhost:5173
  ```

- [ ] **Environment variables** are set
  - `backend/.env.local` exists with all required keys
  - `frontend/.env` exists with correct URLs

- [ ] **Dependencies** are installed
  - Backend: `pip list` shows all required packages
  - Frontend: `npm list` shows all required packages

---

## Troubleshooting

### Common Issues

#### 1. Port Already in Use

**Error:** `Address already in use` or `Port 8000 is already in use`

**Solution:**
```bash
# Find process using port 8000
lsof -ti:8000

# Kill the process
kill -9 $(lsof -ti:8000)

# Or for other ports
lsof -ti:5432  # PostgreSQL
lsof -ti:6379  # Redis
lsof -ti:5173  # Frontend
```

#### 2. Database Connection Failed

**Error:** `could not connect to server` or `database does not exist`

**Solution:**
```bash
# Check if PostgreSQL is running
brew services list | grep postgresql  # macOS
sudo systemctl status postgresql      # Linux

# Start PostgreSQL
brew services start postgresql  # macOS
sudo systemctl start postgresql # Linux

# Run database setup
cd backend
python setup_database.py
```

#### 3. Redis Connection Failed

**Error:** `Connection refused` or `Redis server not running`

**Solution:**
```bash
# Check if Redis is running
redis-cli ping  # Should return: PONG

# Start Redis
redis-server

# Or as service (macOS)
brew services start redis

# Run Redis setup
cd backend
python setup_redis.py
```

#### 4. Missing API Keys

**Error:** `SPEECHMATICS_API_KEY is required` or similar

**Solution:**
1. Check `backend/.env.local` exists
2. Verify all required keys are set:
   - `SPEECHMATICS_API_KEY`
   - `OPENAI_API_KEY`
   - `LIVEKIT_API_KEY`
   - `LIVEKIT_API_SECRET`
3. Restart the backend server

#### 5. WebSocket Connection Failed

**Error:** Frontend shows "WebSocket Disconnected"

**Solution:**
```bash
# Verify backend is running
curl http://localhost:8000/health

# Check WebSocket endpoint
curl -i -N -H "Connection: Upgrade" -H "Upgrade: websocket" http://localhost:8000/ws/transcripts

# Check browser console for specific errors
# Common issues:
# - CORS errors: Check CORS settings in api_server.py
# - Connection refused: Backend not running
# - 404: Wrong WebSocket URL
```

#### 6. Frontend Not Loading

**Error:** White/blank page or 404

**Solution:**
```bash
# Check if frontend is running
curl http://localhost:5173

# Check browser console (F12) for errors
# Common issues:
# - JavaScript errors
# - Missing environment variables
# - Build errors

# Rebuild frontend
cd frontend
rm -rf node_modules
npm install
npm run dev
```

#### 7. Import Errors in Backend

**Error:** `ModuleNotFoundError` or `ImportError`

**Solution:**
```bash
cd backend

# Reinstall dependencies
pip install -r requirements.txt

# Or using uv
uv sync

# Check Python version
python --version  # Should be 3.12+

# For numpy/sklearn issues
pip install "numpy<2.0" "protobuf<6.0"
```

#### 8. LiveKit Agent Not Connecting

**Error:** Agent not connecting to rooms

**Solution:**
1. Verify LiveKit credentials in `backend/.env.local`
2. Check LiveKit server is accessible:
   ```bash
   curl https://your-livekit-url.livekit.cloud
   ```
3. Verify agent is running:
   ```bash
   ps aux | grep "python.*main.py"
   ```
4. Check logs in terminal or `logs/livekit.log`

#### 9. Transcripts Not Appearing

**Error:** No transcripts showing in frontend

**Solution:**
1. Check WebSocket connection (browser console)
2. Verify backend is receiving audio:
   - Check backend logs
   - Check LiveKit agent logs
3. Verify Speechmatics API key is valid
4. Check browser console for WebSocket messages

### Getting Help

If you encounter issues not covered here:

1. **Check Logs:**
   ```bash
   # Backend logs
   tail -f logs/backend.log
   
   # LiveKit logs
   tail -f logs/livekit.log
   
   # Frontend logs (in terminal where npm run dev is running)
   ```

2. **Check Service Status:**
   ```bash
   ./check_services.sh
   ```

3. **Verify Environment:**
   ```bash
   # Backend
   cd backend
   python -c "from dotenv import load_dotenv; import os; load_dotenv('.env.local'); print('Keys:', list(os.environ.keys()))"
   
   # Frontend
   cd frontend
   cat .env
   ```

4. **Test Individual Components:**
   - Test database: `psql -U postgres -d dialogue_db -c "SELECT 1"`
   - Test Redis: `redis-cli ping`
   - Test API: `curl http://localhost:8000/health`
   - Test WebSocket: Use browser console test above

---

## Quick Reference

### Start Everything

**Option 1: TMUX (Recommended)**
```bash
./start_tmux.sh
```

**Option 2: Background Processes**
```bash
./start_app.sh
```

### Stop Everything

**If using TMUX:**
```bash
./stop_tmux.sh
```

**If using background processes:**
```bash
./stop_app.sh
```

### Check Status
```bash
./check_services.sh
```

### Access Points
- **Frontend:** http://localhost:5173
- **Backend API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs
- **Health Check:** http://localhost:8000/health

### Key Commands
```bash
# TMUX (if using tmux startup)
./start_tmux.sh                # Start all services in tmux
./stop_tmux.sh                 # Stop all services in tmux
tmux attach -t dialogue-gen    # Reattach to tmux session
tmux kill-session -t dialogue-gen  # Kill tmux session

# Backend
cd backend
python start_server.py          # Start API server
python main.py dev              # Start LiveKit agent
python setup_database.py        # Setup database
python setup_redis.py           # Setup Redis

# Frontend
cd frontend
npm run dev                     # Start dev server
npm run build                   # Build for production

# Services
brew services start postgresql  # Start PostgreSQL (macOS)
brew services start redis       # Start Redis (macOS)
redis-server                    # Start Redis manually
```

---

## Next Steps

After successful setup and testing:

1. **Generate LiveKit Tokens:** Set up token generation endpoint or use LiveKit dashboard
2. **Test with Multiple Speakers:** Invite others to test multi-speaker transcription
3. **Review Transcripts:** Check saved transcripts in Redis or database
4. **Monitor Performance:** Watch logs for any performance issues
5. **Customize Configuration:** Adjust settings in `backend/config.py` and environment files

---

**Happy Testing! 🚀**

