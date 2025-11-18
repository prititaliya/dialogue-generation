# Startup Guide - Dialogue Generation Application

## Prerequisites Checklist

Before starting the application, ensure these services are running:

### 1. PostgreSQL Database
**Purpose:** User authentication and user data storage

**Check if running:**
```bash
# macOS
brew services list | grep postgresql

# Or check if port 5432 is in use
lsof -ti:5432
```

**Start if not running:**
```bash
# macOS (Homebrew)
brew services start postgresql

# Linux
sudo systemctl start postgresql

# Or manually
postgres -D /usr/local/var/postgres
```

**Setup database (first time only):**
```bash
cd backend
python setup_database.py
```

---

### 2. Redis Server
**Purpose:** Vector database for transcript storage and persistence

**Check if running:**
```bash
redis-cli ping
# Should return: PONG
```

**Start if not running:**
```bash
# Option 1: Using Homebrew service (macOS)
brew services start redis

# Option 2: Manual start
redis-server

# Option 3: Docker
docker run -d --name redis-stack -p 6379:6379 redis/redis-stack:latest
```

**Setup Redis (first time only):**
```bash
cd backend
python setup_redis.py
```

---

### 3. Backend API Server
**Purpose:** Main API server (FastAPI) for authentication, transcript management, and WebSocket connections

**Start:**
```bash
cd backend
python start_server.py
```

**Or manually:**
```bash
cd backend
uvicorn api_server:app --host 0.0.0.0 --port 8000 --reload
```

**Verify it's running:**
- Open: http://localhost:8000/docs
- Should show FastAPI documentation

---

### 4. LiveKit Agent (for recording)
**Purpose:** Handles audio recording and transcription

**Start (development mode):**
```bash
cd backend
python main.py dev
```

**Or production mode:**
```bash
cd backend
python main.py start
```

---

### 5. Frontend (if running locally)
**Purpose:** Web interface

**Start:**
```bash
cd frontend
npm install  # First time only
npm run dev
```

**Verify it's running:**
- Open: http://localhost:5173 (or the port shown in terminal)

---

## Quick Start Commands

### Terminal 1: PostgreSQL
```bash
brew services start postgresql  # macOS
# OR
sudo systemctl start postgresql  # Linux
```

### Terminal 2: Redis
```bash
redis-server
# OR
brew services start redis  # macOS
```

### Terminal 3: Backend API Server
```bash
cd backend
python start_server.py
```

### Terminal 4: LiveKit Agent
```bash
cd backend
python main.py dev
```

### Terminal 5: Frontend (optional, if running locally)
```bash
cd frontend
npm run dev
```

---

## Verification Checklist

After starting all services, verify:

1. **PostgreSQL:**
   ```bash
   psql -U postgres -c "SELECT 1"
   ```

2. **Redis:**
   ```bash
   redis-cli ping
   # Should return: PONG
   ```

3. **Backend API:**
   ```bash
   curl http://localhost:8000/health
   # Should return: {"status": "healthy", ...}
   ```

4. **Health Checks:**
   - Database: http://localhost:8000/health/db
   - Vector DB: http://localhost:8000/health/vector-db

---

## Troubleshooting

### PostgreSQL not starting?
- Check if port 5432 is already in use
- Verify PostgreSQL is installed: `which postgres`
- Check logs: `brew services list` (macOS)

### Redis not starting?
- Check if port 6379 is already in use
- Verify Redis is installed: `which redis-server`
- Try: `redis-server --port 6380` (use different port)

### Backend API errors?
- Check if port 8000 is already in use
- Verify all dependencies: `pip install -r requirements.txt`
- Check logs in terminal

### Vector DB not working?
- Run: `python backend/setup_redis.py`
- Check: `curl http://localhost:8000/health/vector-db`
- Ensure Redis is running: `redis-cli ping`

---

## Environment Variables

Make sure you have a `.env.local` file in the `backend/` directory with:

```env
# Database
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/dialogue_db

# Redis
REDIS_URL=redis://localhost:6379
REDIS_INDEX_NAME=transcripts:index

# LiveKit
LIVEKIT_URL=wss://voice-agent-dsp63yns.livekit.cloud
LIVEKIT_API_KEY=your_api_key
LIVEKIT_API_SECRET=your_api_secret

# Speechmatics (for transcription)
SPEECHMATICS_API_KEY=your_speechmatics_key

# JWT
JWT_SECRET_KEY=your-secret-key-change-in-production
```

---

## Summary

**Minimum required services:**
1. ✅ PostgreSQL (for authentication)
2. ✅ Redis (for transcript storage)
3. ✅ Backend API Server
4. ✅ LiveKit Agent (for recording)

**Optional:**
- Frontend (if running locally, otherwise use production build)

All services must be running for the application to work properly!

