# Quick Start Guide

## 🚀 Fastest Way to Start (Automated)

```bash
./start_app.sh
```

This script will:
- Check and start PostgreSQL & Redis if needed
- Start Backend API Server
- Start LiveKit Agent
- Start Frontend (if npm is available)

To stop everything:
```bash
./stop_app.sh
```

---

## 📋 Manual Startup (Step by Step)

### Prerequisites Check
```bash
./check_services.sh
```

### Step 1: Start PostgreSQL
```bash
brew services start postgresql
# First time only: cd backend && python setup_database.py
```

### Step 2: Start Redis
```bash
redis-server
# First time only: cd backend && python setup_redis.py
```

### Step 3: Start Backend API Server
```bash
cd backend
python start_server.py
```
**Keep this terminal open!**

### Step 4: Start LiveKit Agent (New Terminal)
```bash
cd backend
python main.py dev
```
**Keep this terminal open!**

### Step 5: Start Frontend (New Terminal, Optional)
```bash
cd frontend
npm install  # First time only
npm run dev
```
**Keep this terminal open!**

---

## 🌐 Access the Application

- **Frontend:** http://localhost:5173
- **Backend API:** http://localhost:8000
- **API Documentation:** http://localhost:8000/docs
- **Health Check:** http://localhost:8000/health

---

## ✅ Verify Everything is Running

```bash
./check_services.sh
```

Should show:
- ✅ PostgreSQL: Running
- ✅ Redis: Running  
- ✅ Backend API: Running
- ✅ LiveKit Agent: Running

---

## 🛑 Stop Everything

**Option 1: Use the stop script**
```bash
./stop_app.sh
```

**Option 2: Manual stop**
- Press `Ctrl+C` in each terminal where services are running
- Or kill processes: `pkill -f "python.*start_server.py"` and `pkill -f "python.*main.py"`

---

## 📝 First Time Setup

1. **Install dependencies:**
   ```bash
   cd backend
   pip install -r requirements.txt
   
   cd ../frontend
   npm install
   ```

2. **Setup databases:**
   ```bash
   cd backend
   python setup_database.py  # PostgreSQL
   python setup_redis.py      # Redis
   ```

3. **Configure environment:**
   - Create `backend/.env.local` with your API keys
   - See `STARTUP_GUIDE.md` for details

---

## 🐛 Troubleshooting

**Services won't start?**
- Check ports: `lsof -ti:8000` (backend), `lsof -ti:5432` (PostgreSQL), `lsof -ti:6379` (Redis)
- Check logs in `logs/` directory

**Can't connect to database?**
- Verify PostgreSQL is running: `brew services list | grep postgresql`
- Run setup: `cd backend && python setup_database.py`

**Can't connect to Redis?**
- Verify Redis is running: `redis-cli ping`
- Run setup: `cd backend && python setup_redis.py`

**Frontend not loading?**
- Check if backend is running: `curl http://localhost:8000/health`
- Check browser console for errors

---

## 📚 More Information

- Full setup guide: `STARTUP_GUIDE.md`
- Service status: `./check_services.sh`

