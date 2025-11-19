#!/bin/bash
# Start all services in tmux panes for easy monitoring

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if we're in the right directory
if [ ! -d "backend" ] || [ ! -d "frontend" ]; then
    echo -e "${RED}❌ Error: Please run this script from the project root directory${NC}"
    exit 1
fi

# Check if tmux is installed
if ! command -v tmux &> /dev/null; then
    echo -e "${RED}❌ tmux is not installed${NC}"
    echo "Install it with:"
    echo "  macOS: brew install tmux"
    echo "  Linux: sudo apt-get install tmux"
    exit 1
fi

# Session name
SESSION_NAME="dialogue-gen"

# Function to check if a service is running
check_service() {
    local service_name=$1
    local check_command=$2
    
    if eval "$check_command" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ $service_name is running${NC}"
        return 0
    else
        echo -e "${YELLOW}⚠️  $service_name is not running${NC}"
        return 1
    fi
}

echo -e "${BLUE}=========================================="
echo "  Dialogue Generation - TMUX Startup"
echo "==========================================${NC}"
echo ""

# Check prerequisites
echo "Checking prerequisites..."
echo ""

# Check PostgreSQL
if ! check_service "PostgreSQL" "lsof -ti:5432"; then
    echo -e "${YELLOW}⚠️  PostgreSQL is not running${NC}"
    echo "   Starting PostgreSQL..."
    if command -v brew &> /dev/null; then
        brew services start postgresql 2>/dev/null || echo -e "${RED}   Failed to start PostgreSQL${NC}"
        sleep 2
    else
        echo -e "${YELLOW}   Please start PostgreSQL manually: brew services start postgresql${NC}"
    fi
fi

# Check Redis
if ! check_service "Redis" "redis-cli ping 2>/dev/null | grep -q PONG"; then
    echo -e "${YELLOW}⚠️  Redis is not running${NC}"
    echo "   Starting Redis..."
    if command -v redis-server &> /dev/null; then
        redis-server --daemonize yes 2>/dev/null || echo -e "${RED}   Failed to start Redis${NC}"
        sleep 2
    else
        echo -e "${YELLOW}   Please start Redis manually: redis-server${NC}"
    fi
fi

echo ""
echo -e "${BLUE}=========================================="
echo "Starting Services in TMUX..."
echo "==========================================${NC}"
echo ""

# Kill existing session if it exists
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo -e "${YELLOW}⚠️  Existing tmux session '$SESSION_NAME' found${NC}"
    read -p "Kill existing session and start fresh? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        tmux kill-session -t "$SESSION_NAME"
        echo -e "${GREEN}✅ Killed existing session${NC}"
    else
        echo -e "${BLUE}Attaching to existing session...${NC}"
        echo "Use Ctrl+B then D to detach"
        sleep 2
        tmux attach-session -t "$SESSION_NAME"
        exit 0
    fi
fi

# Create new tmux session
tmux new-session -d -s "$SESSION_NAME" -x 200 -y 50

# Set up pane layout: 4 panes in a 2x2 grid
# Pane 0: Backend API (top-left)
# Pane 1: LiveKit Agent (top-right)
# Pane 2: Frontend (bottom-left)
# Pane 3: Status/Monitor (bottom-right)

# Split window into 2 panes (horizontal split)
tmux split-window -h -t "$SESSION_NAME"

# Split left pane into 2 (vertical split)
tmux split-window -v -t "$SESSION_NAME:0.0"

# Split right pane into 2 (vertical split)
tmux split-window -v -t "$SESSION_NAME:0.1"

# Even out pane sizes
tmux select-layout -t "$SESSION_NAME" tiled

# Pane 0: Backend API Server
echo -e "${GREEN}🚀 Starting Backend API Server in pane 0...${NC}"
tmux send-keys -t "$SESSION_NAME:0.0" "cd backend" C-m
tmux send-keys -t "$SESSION_NAME:0.0" "echo '=== Backend API Server ==='" C-m
tmux send-keys -t "$SESSION_NAME:0.0" "python start_server.py" C-m

# Pane 1: LiveKit Agent
echo -e "${GREEN}🎙️  Starting LiveKit Agent in pane 1...${NC}"
tmux send-keys -t "$SESSION_NAME:0.1" "cd backend" C-m
tmux send-keys -t "$SESSION_NAME:0.1" "echo '=== LiveKit Agent ==='" C-m
tmux send-keys -t "$SESSION_NAME:0.1" "sleep 3" C-m
tmux send-keys -t "$SESSION_NAME:0.1" "python main.py dev" C-m

# Pane 2: Frontend
echo -e "${GREEN}🌐 Starting Frontend in pane 2...${NC}"
tmux send-keys -t "$SESSION_NAME:0.2" "cd frontend" C-m
tmux send-keys -t "$SESSION_NAME:0.2" "echo '=== Frontend Dev Server ==='" C-m
tmux send-keys -t "$SESSION_NAME:0.2" "sleep 5" C-m
tmux send-keys -t "$SESSION_NAME:0.2" "npm run dev" C-m

# Pane 3: Status/Monitor
echo -e "${GREEN}📊 Starting Status Monitor in pane 3...${NC}"
tmux send-keys -t "$SESSION_NAME:0.3" "echo '=== Service Status Monitor ==='" C-m
tmux send-keys -t "$SESSION_NAME:0.3" "echo ''" C-m
tmux send-keys -t "$SESSION_NAME:0.3" "echo 'Services:'" C-m
tmux send-keys -t "$SESSION_NAME:0.3" "echo '  • Backend API:    http://localhost:8000'" C-m
tmux send-keys -t "$SESSION_NAME:0.3" "echo '  • API Docs:       http://localhost:8000/docs'" C-m
tmux send-keys -t "$SESSION_NAME:0.3" "echo '  • Frontend:       http://localhost:5173'" C-m
tmux send-keys -t "$SESSION_NAME:0.3" "echo ''" C-m
tmux send-keys -t "$SESSION_NAME:0.3" "echo 'Health Checks:'" C-m
tmux send-keys -t "$SESSION_NAME:0.3" "echo '  curl http://localhost:8000/health'" C-m
tmux send-keys -t "$SESSION_NAME:0.3" "echo ''" C-m
tmux send-keys -t "$SESSION_NAME:0.3" "echo 'TMUX Controls:'" C-m
tmux send-keys -t "$SESSION_NAME:0.3" "echo '  Ctrl+B then Arrow Keys - Navigate panes'" C-m
tmux send-keys -t "$SESSION_NAME:0.3" "echo '  Ctrl+B then D - Detach (keeps running)'" C-m
tmux send-keys -t "$SESSION_NAME:0.3" "echo '  Ctrl+B then X - Close current pane'" C-m
tmux send-keys -t "$SESSION_NAME:0.3" "echo '  tmux attach -t $SESSION_NAME - Reattach'" C-m
tmux send-keys -t "$SESSION_NAME:0.3" "echo ''" C-m
tmux send-keys -t "$SESSION_NAME:0.3" "echo 'Monitoring services... (Press Ctrl+C to stop)'" C-m
tmux send-keys -t "$SESSION_NAME:0.3" "echo ''" C-m

# Create a monitoring loop in the status pane
tmux send-keys -t "$SESSION_NAME:0.3" "while true; do" C-m
tmux send-keys -t "$SESSION_NAME:0.3" "  echo '--- Status Check ---'" C-m
tmux send-keys -t "$SESSION_NAME:0.3" "  echo -n 'Backend API: '; curl -s http://localhost:8000/health > /dev/null && echo '✅ Running' || echo '❌ Not responding'" C-m
tmux send-keys -t "$SESSION_NAME:0.3" "  echo -n 'PostgreSQL: '; lsof -ti:5432 > /dev/null && echo '✅ Running' || echo '❌ Not running'" C-m
tmux send-keys -t "$SESSION_NAME:0.3" "  echo -n 'Redis: '; redis-cli ping 2>/dev/null | grep -q PONG && echo '✅ Running' || echo '❌ Not running'" C-m
tmux send-keys -t "$SESSION_NAME:0.3" "  echo ''" C-m
tmux send-keys -t "$SESSION_NAME:0.3" "  sleep 10" C-m
tmux send-keys -t "$SESSION_NAME:0.3" "done" C-m

# Set window title
tmux rename-window -t "$SESSION_NAME:0" "Dialogue Generation"

# Select the first pane (Backend API)
tmux select-pane -t "$SESSION_NAME:0.0"

# Wait a moment for services to start
sleep 3

echo ""
echo -e "${BLUE}=========================================="
echo -e "${GREEN}✅ All Services Started in TMUX!${NC}"
echo -e "${BLUE}==========================================${NC}"
echo ""
echo -e "${GREEN}TMUX Session:${NC} $SESSION_NAME"
echo ""
echo -e "${BLUE}Pane Layout:${NC}"
echo "  ┌─────────────┬─────────────┐"
echo "  │ Backend API │ LiveKit     │"
echo "  │ (port 8000) │ Agent       │"
echo "  ├─────────────┼─────────────┤"
echo "  │ Frontend    │ Status      │"
echo "  │ (port 5173)  │ Monitor     │"
echo "  └─────────────┴─────────────┘"
echo ""
echo -e "${BLUE}TMUX Controls:${NC}"
echo "  • ${GREEN}Ctrl+B then Arrow Keys${NC} - Navigate between panes"
echo "  • ${GREEN}Ctrl+B then D${NC} - Detach (keeps services running)"
echo "  • ${GREEN}Ctrl+B then X${NC} - Close current pane"
echo "  • ${GREEN}Ctrl+B then Z${NC} - Zoom current pane (full screen)"
echo "  • ${GREEN}Ctrl+B then [${NC} - Scroll mode (use arrow keys, q to exit)"
echo ""
echo -e "${BLUE}Reattach to session:${NC}"
echo "  tmux attach -t $SESSION_NAME"
echo ""
echo -e "${BLUE}Kill session (stops all services):${NC}"
echo "  tmux kill-session -t $SESSION_NAME"
echo ""
echo -e "${BLUE}Access Points:${NC}"
echo "  • Frontend:    http://localhost:5173"
echo "  • Backend API: http://localhost:8000"
echo "  • API Docs:    http://localhost:8000/docs"
echo "  • Health:      http://localhost:8000/health"
echo ""

# Attach to the session
echo -e "${GREEN}Attaching to tmux session...${NC}"
echo -e "${YELLOW}Press Ctrl+B then D to detach (services keep running)${NC}"
echo ""
sleep 2

tmux attach-session -t "$SESSION_NAME"

