# Dialogue Generation System

A real-time dialogue transcription system with WebRTC integration, featuring automatic speaker identification and multi-speaker conversation transcription with speaker labels.

## Project Structure

```
dialogue-generation/
├── backend/          # Python backend with LiveKit agents
│   ├── main.py       # LiveKit agent entrypoint
│   ├── api_server.py # FastAPI server with WebSocket
│   ├── start_server.py # Server startup script
│   └── ...
├── frontend/         # React frontend application
│   ├── src/
│   │   ├── components/
│   │   ├── services/
│   │   └── ...
│   └── ...
└── README.md
```

## Features

- 🎤 Real-time speech-to-text transcription
- 👥 Automatic speaker diarization (identifies who said what)
- 🤖 AI-powered speaker name extraction
- 📝 Real-time transcript display in web UI
- 🔄 WebSocket streaming for live updates
- 🎥 WebRTC integration with LiveKit
- 💾 Automatic transcript saving

## Prerequisites

- Python 3.12 or higher
- Node.js 18+ and npm
- LiveKit server (local or cloud)
- API keys for:
  - Speechmatics (for STT and diarization)
  - OpenAI (for speaker name extraction)

## Quick Start

### Backend Setup

1. Navigate to the backend directory:
```bash
cd backend
```

2. Install dependencies:
```bash
# Using uv (recommended)
uv sync

# Or using pip
pip install -r requirements.txt
```

3. Set up environment variables in `.env.local`:
```bash
SPEECHMATICS_API_KEY=your_speechmatics_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
LIVEKIT_URL=ws://localhost:7880
LIVEKIT_API_KEY=your_livekit_api_key
LIVEKIT_API_SECRET=your_livekit_api_secret
```

4. Start the API server (keep this running):
```bash
python start_server.py
```

You should see:
```
🚀 API server started on http://localhost:8000
📡 WebSocket endpoint: ws://localhost:8000/ws/transcripts
```

5. In **another terminal**, start the LiveKit agent:
```bash
cd backend
python main.py dev
```

**Important:** You need **3 terminals** running:
1. API Server (`python start_server.py`)
2. LiveKit Agent (`python main.py dev`)
3. Frontend (`npm run dev` in frontend folder)

### Frontend Setup

1. Navigate to the frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Create `.env` file:
```bash
VITE_API_URL=ws://localhost:8000
VITE_LIVEKIT_URL=ws://localhost:7880
```

4. Start the development server:
```bash
npm run dev
```

5. Open `http://localhost:5173` in your browser

## Usage

### Workflow

1. **Start Services**: Start both the backend API server and LiveKit agent
2. **Open Frontend**: Open the web application in your browser
3. **Connect to Room**: Enter a room name and LiveKit access token, then click "Connect"
4. **Sampling Phase**: The system will automatically identify speakers as they introduce themselves
5. **Say "stop sampling"**: When ready, say "stop sampling" to begin transcription
6. **Transcription Phase**: Real-time transcripts will appear in the web UI with speaker labels
7. **Stop Recording**: Say "stop recording" to end the session

### Getting a LiveKit Token

You'll need a LiveKit access token to connect to a room. You can:

1. Use the LiveKit dashboard to generate tokens
2. Use the LiveKit token API
3. Create a simple token server endpoint

Example token generation (Node.js):
```javascript
import { AccessToken } from 'livekit-server-sdk';

const token = new AccessToken(apiKey, apiSecret, {
  identity: 'user-' + Math.random().toString(36).substring(7),
});
token.addGrant({ roomJoin: true, room: 'your-room-name' });
const jwt = await token.toJwt();
```

## Architecture

### Backend

- **LiveKit Agent** (`main.py`): Processes audio from LiveKit rooms, performs speaker diarization, and extracts speaker names
- **FastAPI Server** (`api_server.py`): Provides WebSocket endpoint for real-time transcript streaming
- **Transcript Manager**: Manages transcript state and broadcasts to connected clients

### Frontend

- **LiveKit Service**: Handles WebRTC connection to LiveKit rooms
- **Transcript Service**: Connects to backend WebSocket for transcript updates
- **React Components**: UI for room connection and transcript display

## API Endpoints

- `GET /` - API server status
- `GET /health` - Health check
- `GET /transcripts` - Get all stored transcripts
- `WS /ws/transcripts` - WebSocket endpoint for real-time transcript streaming

## Configuration

### Backend Environment Variables

- `SPEECHMATICS_API_KEY`: Required - Speechmatics API key
- `OPENAI_API_KEY`: Required - OpenAI API key
- `LIVEKIT_URL`: LiveKit server URL (default: `ws://localhost:7880`)
- `LIVEKIT_API_KEY`: LiveKit API key
- `LIVEKIT_API_SECRET`: LiveKit API secret

### Frontend Environment Variables

- `VITE_API_URL`: Backend WebSocket URL (default: `ws://localhost:8000`)
- `VITE_LIVEKIT_URL`: LiveKit server URL (default: `ws://localhost:7880`)

## Troubleshooting

### WebSocket Connection Issues

**Symptom:** Frontend shows "WebSocket Disconnected" or connection fails

**Step 1: Verify API Server is Running**
```bash
# Check if port 8000 is listening
lsof -i :8000

# Or test the health endpoint
curl http://localhost:8000/health
```

**Expected:** `{"status":"healthy"}`

**If not running:**
```bash
cd backend
python start_server.py
```

**Step 2: Test WebSocket Connection**
```bash
cd backend
python test_websocket.py
```

**Expected output:**
```
Connecting to ws://localhost:8000/ws/transcripts...
✅ Connected successfully!
```

**Step 3: Check Browser Console**
1. Open browser DevTools (F12)
2. Go to Console tab
3. Look for:
   - `Attempting to connect to: ws://localhost:8000/ws/transcripts`
   - `✅ WebSocket connected` (success)
   - Error messages (failure)

**Common WebSocket Errors:**
- **Connection refused (code 1006)**: API server not running
- **Connection closed immediately**: Check CORS settings in `api_server.py`
- **Max reconnection attempts**: Server crashed or port blocked

### Backend Issues

1. **"SPEECHMATICS_API_KEY is required"**
   - Make sure `.env.local` exists in the backend directory
   - Verify the API key is correct

2. **WebSocket connection fails**
   - Ensure the API server is running: `python start_server.py`
   - Check firewall settings
   - Verify port 8000 is not in use: `lsof -i :8000`

3. **Agent not connecting to room**
   - Verify LiveKit server is running
   - Check LiveKit credentials in `.env.local`

4. **Import errors (speechmatics, transformers, etc.)**
   - Reinstall dependencies: `pip install -r requirements.txt`
   - Check Python version: `python --version` (needs 3.12+)
   - For numpy/sklearn issues: `pip install "numpy<2.0" "protobuf<6.0"`

### Frontend Issues

1. **WebSocket not connecting**
   - Verify backend API server is running: `python backend/start_server.py`
   - Check `VITE_API_URL` in `.env` (should be `ws://localhost:8000`)
   - Open browser console to see connection errors

2. **White/blank page**
   - Check browser console for JavaScript errors (F12)
   - Verify Vite is running: `npm run dev`
   - Try hard refresh: Cmd+Shift+R (Mac) or Ctrl+Shift+R (Windows)

3. **LiveKit connection fails**
   - Verify LiveKit server is accessible
   - Check token validity
   - Ensure room name matches
   - Check `VITE_LIVEKIT_URL` in `.env`

4. **Page loads but no styling**
   - Tailwind CSS might not be processing
   - Check if `postcss.config.js` exists
   - Restart Vite dev server

## Development

### Backend Development

```bash
cd backend
python main.py dev  # Start agent in development mode
python start_server.py  # Start API server
```

### Frontend Development

```bash
cd frontend
npm run dev  # Start Vite dev server
npm run build  # Build for production
```

## License

[Add your license here]

## Testing WebSocket Connection

To verify the WebSocket is working:

```bash
# Test from command line
cd backend
python test_websocket.py

# Or test in browser
# Open test_websocket.html in your browser
```

## Support

For issues or questions:
1. Check the logs for detailed error messages
2. See `WEBSOCKET_TROUBLESHOOTING.md` for WebSocket-specific issues
3. Verify all services are running (API server, LiveKit agent, frontend)
4. Check browser console (F12) for frontend errors
5. Verify environment variables are set correctly

