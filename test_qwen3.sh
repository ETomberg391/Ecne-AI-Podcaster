#!/bin/bash
# Test Qwen3 TTS API

API_URL="http://127.0.0.1:8000"

echo "Testing Qwen3 TTS API at $API_URL..."
echo ""

# Health check
echo "1. Health Check:"
curl -s "$API_URL/health" | $PYTHON_CMD -m json.tool 2>/dev/null || curl -s "$API_URL/health"
echo ""

# Test TTS with Ryan voice
echo ""
echo "2. Testing TTS with Ryan voice:"
curl -s -X POST "$API_URL/v1/audio/speech" \
  -F "model=qwen3-tts-1.7b-customvoice" \
  -F "input=Hello, this is a test of the Qwen3 text to speech system." \
  -F "voice=Ryan" \
  -F "response_format=wav" \
  -F "speed=1.0" \
  --output /tmp/qwen3_test.wav

if [ -f "/tmp/qwen3_test.wav" ] && [ -s "/tmp/qwen3_test.wav" ]; then
    echo "✓ Audio generated successfully: /tmp/qwen3_test.wav"
    ls -lh /tmp/qwen3_test.wav
else
    echo "✗ Failed to generate audio"
fi

echo ""
echo "Test complete!"
