#!/bin/bash

# Ecne AI Podcaster Launcher
# Starts both the Qwen3 TTS service and the main application

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}Starting Ecne AI Podcaster with Qwen3 TTS...${NC}"
echo ""

# Function to cleanup on exit
cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down services...${NC}"
    if [ -n "$QWEN3_PID" ]; then
        kill $QWEN3_PID 2>/dev/null
        echo "  - Qwen3 TTS service stopped"
    fi
    exit 0
}

trap cleanup SIGINT SIGTERM

# Start Qwen3 TTS Service
echo "1. Starting Qwen3 TTS Service..."
cd EcneAI-Qwen-3-TTS-api
source venv/bin/activate
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --log-level info > ../logs/qwen3_service.log 2>&1 &
QWEN3_PID=$!
cd "$SCRIPT_DIR"

echo "   PID: $QWEN3_PID"
echo "   Log: logs/qwen3_service.log"
echo ""

# Wait for service to be ready
echo "2. Waiting for Qwen3 TTS to be ready..."
for i in {1..30}; do
    if curl -s http://127.0.0.1:8000/health > /dev/null 2>&1; then
        echo -e "${GREEN}   Qwen3 TTS is ready!${NC}"
        break
    fi
    sleep 1
    echo -n "."
done
echo ""

# Check if service is actually running
if ! kill -0 $QWEN3_PID 2>/dev/null; then
    echo -e "${RED}Qwen3 TTS service failed to start!${NC}"
    echo "Check logs/qwen3_service.log for details."
    exit 1
fi

# Launch Control Panel
echo "3. Starting Control Panel..."
echo ""
source venv/bin/activate
python control_panel_app.py

# Cleanup when control panel exits
cleanup
