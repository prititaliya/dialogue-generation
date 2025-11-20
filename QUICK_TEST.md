# Quick Test Reference Card

## 🚀 Fastest Way to Start

### Option 1: TMUX (Recommended - All in one window)
```bash
./start_tmux.sh
```
Starts all services in tmux panes - easy to monitor everything in one terminal!

### Option 2: Background Processes
```bash
./start_app.sh
```

## ✅ Verify Everything is Running

```bash
./check_services.sh
```

## 🛑 Stop Everything

### If using TMUX:
```bash
./stop_tmux.sh
```

### If using background processes:
```bash
./stop_app.sh
```

---

## 📋 Manual Startup (5 Terminals)

### Terminal 1: PostgreSQL
```bash
brew services start postgresql
```

### Terminal 2: Redis
```bash
redis-server
```

### Terminal 3: Backend API
```bash
cd backend
python start_server.py
```

### Terminal 4: LiveKit Agent
```bash
cd backend
python main.py dev
```

### Terminal 5: Frontend
```bash
cd frontend
npm run dev
```

---

## 🔍 Quick Health Checks

```bash
# Backend API
curl http://localhost:8000/health

# Database
curl http://localhost:8000/health/db

# Redis/Vector DB
curl http://localhost:8000/health/vector-db
```

---

## 🌐 Access Points

- **Frontend:** http://localhost:5173
- **API Docs:** http://localhost:8000/docs
- **Health:** http://localhost:8000/health

---

## ⚙️ First Time Setup

1. **Install dependencies:**
   ```bash
   cd backend && pip install -r requirements.txt
   cd ../frontend && npm install
   ```

2. **Setup databases:**
   ```bash
   cd backend
   python setup_database.py
   python setup_redis.py
   ```

3. **Create environment files:**
   - `backend/.env.local` (see TESTING_GUIDE.md)
   - `frontend/.env` (see TESTING_GUIDE.md)

---

## 📖 Full Guide

See **TESTING_GUIDE.md** for complete instructions.

