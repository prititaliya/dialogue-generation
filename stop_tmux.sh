#!/bin/bash
# Stop all services running in tmux session

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

SESSION_NAME="dialogue-gen"

echo -e "${BLUE}=========================================="
echo "  Stopping Dialogue Generation Services"
echo "==========================================${NC}"
echo ""

# Check if session exists
if ! tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo -e "${YELLOW}⚠️  No tmux session '$SESSION_NAME' found${NC}"
    echo "Services may not be running in tmux."
    echo ""
    echo "Checking for other running services..."
    
    # Check for processes
    if pgrep -f "python.*start_server.py" > /dev/null; then
        echo -e "${YELLOW}Found Backend API process, killing...${NC}"
        pkill -f "python.*start_server.py"
    fi
    
    if pgrep -f "python.*main.py.*dev" > /dev/null; then
        echo -e "${YELLOW}Found LiveKit Agent process, killing...${NC}"
        pkill -f "python.*main.py.*dev"
    fi
    
    if pgrep -f "vite.*frontend" > /dev/null; then
        echo -e "${YELLOW}Found Frontend process, killing...${NC}"
        pkill -f "vite.*frontend"
    fi
    
    echo -e "${GREEN}✅ Cleaned up any remaining processes${NC}"
    exit 0
fi

echo -e "${BLUE}Stopping tmux session: $SESSION_NAME${NC}"
echo ""

# Send Ctrl+C to all panes to gracefully stop services
echo "Sending stop signals to all panes..."
tmux send-keys -t "$SESSION_NAME:0.0" C-c 2>/dev/null  # Backend API
tmux send-keys -t "$SESSION_NAME:0.1" C-c 2>/dev/null  # LiveKit Agent
tmux send-keys -t "$SESSION_NAME:0.2" C-c 2>/dev/null  # Frontend
tmux send-keys -t "$SESSION_NAME:0.3" C-c 2>/dev/null  # Status Monitor

# Wait a moment for graceful shutdown
sleep 2

# Kill the session
tmux kill-session -t "$SESSION_NAME" 2>/dev/null

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Successfully stopped tmux session${NC}"
else
    echo -e "${RED}❌ Failed to stop tmux session${NC}"
    echo "You may need to manually kill it: tmux kill-session -t $SESSION_NAME"
fi

echo ""
echo -e "${BLUE}Verifying services are stopped...${NC}"

# Check if services are still running
if lsof -ti:8000 > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  Port 8000 still in use (Backend API may still be running)${NC}"
    echo "   Kill manually: kill \$(lsof -ti:8000)"
fi

if lsof -ti:5173 > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  Port 5173 still in use (Frontend may still be running)${NC}"
    echo "   Kill manually: kill \$(lsof -ti:5173)"
fi

# Check for remaining processes
if pgrep -f "python.*start_server.py" > /dev/null; then
    echo -e "${YELLOW}⚠️  Backend API process still running${NC}"
    pkill -f "python.*start_server.py"
fi

if pgrep -f "python.*main.py.*dev" > /dev/null; then
    echo -e "${YELLOW}⚠️  LiveKit Agent process still running${NC}"
    pkill -f "python.*main.py.*dev"
fi

if pgrep -f "vite" > /dev/null; then
    echo -e "${YELLOW}⚠️  Frontend process still running${NC}"
    pkill -f "vite"
fi

echo ""
echo -e "${GREEN}✅ All services stopped${NC}"
echo ""

