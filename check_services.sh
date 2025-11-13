#!/bin/bash
# Quick service status checker

echo "=== Service Status Check ==="
echo ""

echo "1. PostgreSQL:"
if lsof -ti:5432 > /dev/null 2>&1; then
    echo "   ✅ Running on port 5432"
else
    echo "   ❌ Not running"
    echo "   → Start with: brew services start postgresql"
fi
echo ""

echo "2. Redis:"
if redis-cli ping 2>/dev/null | grep -q PONG; then
    echo "   ✅ Running"
else
    echo "   ❌ Not running"
    echo "   → Start with: redis-server"
fi
echo ""

echo "3. Backend API (port 8000):"
if lsof -ti:8000 > /dev/null 2>&1; then
    echo "   ✅ Running on port 8000"
else
    echo "   ❌ Not running"
    echo "   → Start with: cd backend && python start_server.py"
fi
echo ""

echo "4. LiveKit Agent:"
if ps aux | grep -i "python.*main.py.*dev" | grep -v grep > /dev/null 2>&1; then
    echo "   ✅ Running (agent process detected)"
else
    echo "   ❌ Not running"
    echo "   → Start with: cd backend && python main.py dev"
fi
echo ""
echo "   Note: LiveKit agent connects to LiveKit server (port 7880)"
echo "   The agent itself doesn't listen on a port."
echo ""

