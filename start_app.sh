#!/bin/bash
# Complete application startup script

echo "=========================================="
echo "  Dialogue Generation - Startup Script"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if we're in the right directory
if [ ! -d "backend" ] || [ ! -d "frontend" ]; then
    echo -e "${RED}❌ Error: Please run this script from the project root directory${NC}"
    exit 1
fi

# Function to check if a service is running
check_service() {
    local service_name=$1
    local check_command=$2
    
    if eval "$check_command" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ $service_name is running${NC}"
        return 0
    else
        echo -e "${RED}❌ $service_name is not running${NC}"
        return 1
    fi
}

# Check prerequisites
echo "Checking prerequisites..."
echo ""

# Check PostgreSQL
if check_service "PostgreSQL" "lsof -ti:5432"; then
    :
else
    echo -e "${YELLOW}⚠️  Starting PostgreSQL...${NC}"
    if command -v brew &> /dev/null; then
        brew services start postgresql 2>/dev/null || echo -e "${RED}   Failed to start PostgreSQL${NC}"
        sleep 2
    fi
fi

# Check Redis
if check_service "Redis" "redis-cli ping 2>/dev/null | grep -q PONG"; then
    :
else
    echo -e "${YELLOW}⚠️  Starting Redis...${NC}"
    if command -v redis-server &> /dev/null; then
        redis-server --daemonize yes 2>/dev/null || echo -e "${RED}   Failed to start Redis${NC}"
        sleep 2
    fi
fi

echo ""
echo "=========================================="
echo "Starting Application Services..."
echo "=========================================="
echo ""

# Start Backend API Server
echo -e "${GREEN}🚀 Starting Backend API Server...${NC}"
cd backend

# Check if virtual environment is needed (optional)
if [ -d "venv" ] || [ -d ".venv" ]; then
    echo "   Activating virtual environment..."
    source venv/bin/activate 2>/dev/null || source .venv/bin/activate 2>/dev/null
fi

# Start backend in background
python start_server.py > ../logs/backend.log 2>&1 &
BACKEND_PID=$!
echo "   Backend API started (PID: $BACKEND_PID)"
echo "   Logs: logs/backend.log"
echo "   API Docs: http://localhost:8000/docs"
sleep 3

# Start LiveKit Agent
echo ""
echo -e "${GREEN}🎙️  Starting LiveKit Agent...${NC}"
python main.py dev > ../logs/livekit.log 2>&1 &
LIVEKIT_PID=$!
echo "   LiveKit Agent started (PID: $LIVEKIT_PID)"
echo "   Logs: logs/livekit.log"
sleep 2

cd ..

# Start Frontend (optional - only if npm is available)
if command -v npm &> /dev/null; then
    echo ""
    echo -e "${GREEN}🌐 Starting Frontend...${NC}"
    cd frontend
    
    # Check if node_modules exists
    if [ ! -d "node_modules" ]; then
        echo "   Installing dependencies (first time only)..."
        npm install
    fi
    
    npm run dev > ../logs/frontend.log 2>&1 &
    FRONTEND_PID=$!
    echo "   Frontend started (PID: $FRONTEND_PID)"
    echo "   Logs: logs/frontend.log"
    echo "   URL: http://localhost:5173"
    cd ..
else
    echo ""
    echo -e "${YELLOW}⚠️  npm not found - skipping frontend${NC}"
    echo "   Frontend can be started manually: cd frontend && npm run dev"
fi

# Create logs directory if it doesn't exist
mkdir -p logs

# Save PIDs to file for easy shutdown
echo "$BACKEND_PID" > logs/backend.pid
echo "$LIVEKIT_PID" > logs/livekit.pid
[ ! -z "$FRONTEND_PID" ] && echo "$FRONTEND_PID" > logs/frontend.pid

echo ""
echo "=========================================="
echo -e "${GREEN}✅ Application Started!${NC}"
echo "=========================================="
echo ""
echo "Services running:"
echo "  • Backend API:    http://localhost:8000"
echo "  • API Docs:       http://localhost:8000/docs"
echo "  • LiveKit Agent:  Running (PID: $LIVEKIT_PID)"
if [ ! -z "$FRONTEND_PID" ]; then
    echo "  • Frontend:        http://localhost:5173"
fi
echo ""
echo "To stop all services, run: ./stop_app.sh"
echo "Or manually kill PIDs:"
echo "  kill $BACKEND_PID $LIVEKIT_PID${FRONTEND_PID:+ $FRONTEND_PID}"
echo ""
echo "Logs are in the 'logs/' directory"
echo ""

