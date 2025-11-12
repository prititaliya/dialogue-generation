# WebSocket Troubleshooting Guide

## Issue: WebSocket Not Connecting

### Step 1: Check if API Server is Running

```bash
# Check if port 8000 is in use
lsof -i :8000

# Or test the health endpoint
curl http://localhost:8000/health
```

**Expected output:** `{"status":"healthy"}`

**If not running:** Start the API server:
```bash
cd backend
python start_server.py
```

### Step 2: Verify WebSocket Endpoint

Test the WebSocket connection:
```bash
cd backend
python test_websocket.py
```

**Expected output:**
```
Connecting to ws://localhost:8000/ws/transcripts...
✅ Connected successfully!
```

### Step 3: Check Browser Console

1. Open browser DevTools (F12)
2. Go to Console tab
3. Look for WebSocket connection messages:
   - `Attempting to connect to: ws://localhost:8000/ws/transcripts`
   - `✅ WebSocket connected` (success)
   - Or error messages (failure)

### Step 4: Common Issues

#### Issue: "Connection refused"
**Solution:** API server is not running. Start it with `python backend/start_server.py`

#### Issue: "WebSocket closed with code 1006"
**Solution:** 
- Check if API server crashed
- Check server logs for errors
- Verify CORS is enabled in `api_server.py`

#### Issue: "Max reconnection attempts reached"
**Solution:**
- Ensure API server is running
- Check firewall settings
- Verify port 8000 is not blocked

### Step 5: Manual WebSocket Test

Open `test_websocket.html` in your browser to test the connection directly.

### Step 6: Check API Server Logs

The API server should show:
```
🚀 API server started on http://localhost:8000
📡 WebSocket endpoint: ws://localhost:8000/ws/transcripts
```

When a client connects, you should see:
```
Client connected. Total connections: 1
```

## Quick Fix Checklist

- [ ] API server is running (`python backend/start_server.py`)
- [ ] Port 8000 is accessible
- [ ] No firewall blocking the connection
- [ ] Browser console shows connection attempts
- [ ] CORS is enabled in `api_server.py`

## Testing Commands

```bash
# Test HTTP endpoint
curl http://localhost:8000/health

# Test WebSocket (Python)
cd backend
python test_websocket.py

# Test WebSocket (Browser)
# Open test_websocket.html in browser
```

