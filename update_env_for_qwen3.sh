#!/bin/bash
# Update .env file for Qwen3 TTS

ENV_FILE="/home/dundell2/Desktop/dev/ComfyUI-Qwen3-TTS/workflow/Ecne-AI-Podcaster/.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "Creating new .env file..."
    cp "/home/dundell2/Desktop/dev/ComfyUI-Qwen3-TTS/workflow/Ecne-AI-Podcaster/settings/env.example" "$ENV_FILE"
fi

# Update TTS provider to Qwen3
sed -i 's/^TTS_PROVIDER=.*/TTS_PROVIDER="qwen3"/' "$ENV_FILE"

echo "Updated $ENV_FILE for Qwen3 TTS"
echo "TTS_PROVIDER is now set to 'qwen3'"
