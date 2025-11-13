#!/bin/bash
# Stop all application services

echo "Stopping Dialogue Generation services..."

# Kill processes from PID files
if [ -f "logs/backend.pid" ]; then
    PID=$(cat logs/backend.pid)
    if ps -p $PID > /dev/null 2>&1; then
        kill $PID 2>/dev/null
        echo "✅ Stopped Backend API (PID: $PID)"
    fi
    rm logs/backend.pid
fi

if [ -f "logs/livekit.pid" ]; then
    PID=$(cat logs/livekit.pid)
    if ps -p $PID > /dev/null 2>&1; then
        kill $PID 2>/dev/null
        echo "✅ Stopped LiveKit Agent (PID: $PID)"
    fi
    rm logs/livekit.pid
fi

if [ -f "logs/frontend.pid" ]; then
    PID=$(cat logs/frontend.pid)
    if ps -p $PID > /dev/null 2>&1; then
        kill $PID 2>/dev/null
        echo "✅ Stopped Frontend (PID: $PID)"
    fi
    rm logs/frontend.pid
fi

# Also kill any remaining processes
pkill -f "python.*start_server.py" 2>/dev/null
pkill -f "python.*main.py.*dev" 2>/dev/null
pkill -f "vite.*frontend" 2>/dev/null

echo "✅ All services stopped"

