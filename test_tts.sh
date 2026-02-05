#!/bin/bash
# Test Qwen3 TTS functionality

echo "Testing Qwen3 TTS..."

# Test health endpoint
if curl -s http://127.0.0.1:8000/health > /dev/null 2>&1; then
    echo "✓ Qwen3 TTS service is running"
else
    echo "✗ Qwen3 TTS service is not running"
    echo "  Start it with: ./start_qwen3.sh"
    exit 1
fi

# Test speakers endpoint
echo ""
echo "Available speakers:"
curl -s http://127.0.0.1:8000/v1/speakers | $PYTHON_CMD -m json.tool 2>/dev/null || curl -s http://127.0.0.1:8000/v1/speakers

echo ""
echo "Test complete!"
