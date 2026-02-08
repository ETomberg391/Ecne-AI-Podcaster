#!/bin/bash
# Quick start for Qwen3 TTS service only

cd "$(dirname "$0")/EcneAI-Qwen-3-TTS-api" || exit 1
source venv/bin/activate
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --log-level info
