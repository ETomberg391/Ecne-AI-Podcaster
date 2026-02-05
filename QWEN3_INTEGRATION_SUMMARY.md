# Qwen3 TTS Integration - Implementation Summary

## Overview

The Ecne-AI-Podcaster project has been successfully integrated with **Qwen3 TTS** as the **primary/default TTS provider**, while maintaining **Orpheus TTS** as a secondary/alternative option.

## What Was Implemented

### 1. TTS Provider Architecture

New provider system in [`functions/tts/providers/`](functions/tts/providers/):

| File | Purpose |
|------|---------|
| [`__init__.py`](functions/tts/providers/__init__.py) | Provider factory and registry |
| [`base.py`](functions/tts/providers/base.py) | Abstract base class `TTSProvider` |
| [`qwen3.py`](functions/tts/providers/qwen3.py) | Qwen3 TTS provider implementation |
| [`orpheus.py`](functions/tts/providers/orpheus.py) | Orpheus TTS provider implementation |

### 2. New CLI Arguments

Added to [`functions/tts/args.py`](functions/tts/args.py):

```bash
# Provider selection
--tts-provider {qwen3,orpheus}     # Default: qwen3
--qwen3-port PORT                  # Default: 8000
--qwen3-model MODEL                # Default: qwen3-tts-1.7b-customvoice
--orpheus-port PORT                # Default: 5005

# Qwen3-specific options
--qwen3-instruction {happy,sad,whisper,...}  # Emotion/style control
--qwen3-temperature TEMP           # Default: 0.9
```

### 3. Updated API Module

[`functions/tts/api.py`](functions/tts/api.py) changes:

- Added `get_tts_provider()` - Provider singleton management
- Added `generate_audio_segment_with_provider()` - Provider-aware generation
- Added `check_tts_health()` - Health check utility
- Maintains backward compatibility with existing `generate_audio_segment()`

### 4. Voice Configuration Files

New Qwen3 voice configs in [`settings/voices/`](settings/voices/):

| Voice | Language | Gender | Recommended For |
|-------|----------|--------|-----------------|
| `ryan.yaml` | English | Male | **Host** (default) |
| `aiden.yaml` | English | Male | Alternative host |
| `serena.yaml` | Chinese/English | Female | **Guest** (default) |
| `vivian.yaml` | Chinese/English | Female | Alternative guest |
| `sohee.yaml` | Korean/English | Female | Korean content |
| `dylan.yaml` | Chinese | Male | Chinese content |
| `uncle_fu.yaml` | Chinese | Male | Mature Chinese |
| `ono_anna.yaml` | Japanese | Female | Japanese content |

### 5. Environment Configuration

Updated [`settings/env.example`](settings/env.example) with new variables:

```bash
# TTS Provider
TTS_PROVIDER="qwen3"
QWEN3_API_HOST="127.0.0.1"
QWEN3_API_PORT=8000
QWEN3_HOST_VOICE="Ryan"
QWEN3_GUEST_VOICE="Serena"

# Legacy Orpheus settings
ORPHEUS_API_HOST="127.0.0.1"
ORPHEUS_API_PORT=5005
ORPHEUS_HOST_VOICE="leo"
ORPHEUS_GUEST_VOICE="tara"
```

### 6. Setup Scripts

Created dedicated Qwen3 setup scripts:

- [`setup_qwen3.sh`](setup_qwen3.sh) - Linux/macOS setup
- [`setup_qwen3.bat`](setup_qwen3.bat) - Windows setup

These scripts:
- Install Qwen3 TTS API dependencies
- Detect GPU and install appropriate PyTorch
- Create helper scripts (`start_qwen3.sh/bat`, `test_qwen3.sh/bat`)
- Optionally create systemd service (Linux)

### 7. Requirements File

Created [`requirements_qwen3.txt`](requirements_qwen3.txt) with:
- FastAPI/uvicorn for API server
- PyTorch, transformers, qwen-tts
- Audio processing libraries
- Model download utilities

## Default Behavior Changes

| Aspect | Before | After |
|--------|--------|-------|
| **Default Provider** | Orpheus | Qwen3 |
| **Default Host Voice** | leo | Ryan |
| **Default Guest Voice** | tara | Serena |
| **Default Port** | 5005 | 8000 (Qwen3) |
| **Speed Range** | 0.5-1.5x | 0.5-2.0x (Qwen3) |

## Backward Compatibility

✅ **Fully maintained** - Existing scripts work without changes:

```bash
# Old Orpheus usage still works
python script_builder.py --script podcast.txt --tts-provider orpheus

# Legacy arguments still supported
python script_builder.py --script podcast.txt --port 5005  # Maps to --orpheus-port
```

## Usage Examples

### Basic Usage (Qwen3 Default)

```bash
# Uses Ryan (host) and Serena (guest) by default
python script_builder.py --script podcast.txt

# Explicit Qwen3 with specific voices
python script_builder.py --script podcast.txt --tts-provider qwen3 \
  --host-voice Ryan --guest-voice Serena
```

### Using Orpheus (Legacy)

```bash
# Use Orpheus with original voices
python script_builder.py --script podcast.txt --tts-provider orpheus \
  --host-voice leo --guest-voice tara
```

### Voice Cloning with Qwen3

```bash
# 1. Clone a voice
 curl -X POST http://localhost:8000/v1/voices \
   -F "name=Custom Voice" \
   -F "voice_sample=@my_voice.wav" \
   -F "voice_sample_text=Original text in sample"

# 2. Use cloned voice (returns voice_id like "voice_abc123")
python script_builder.py --script podcast.txt --guest-voice voice_abc123
```

### Emotion Control (Qwen3 only)

```bash
# Add emotion to speech
python script_builder.py --script podcast.txt --qwen3-instruction happy
python script_builder.py --script podcast.txt --qwen3-instruction whisper
```

## Setup Instructions

### Quick Start (Linux/macOS)

```bash
# 1. Run Qwen3 setup
./setup_qwen3.sh

# 2. Start Qwen3 server
./start_qwen3.sh

# 3. In another terminal, test
./test_qwen3.sh

# 4. Update .env
./update_env_for_qwen3.sh
```

### Quick Start (Windows)

```batch
:: 1. Run Qwen3 setup
setup_qwen3.bat

:: 2. Start Qwen3 server
start_qwen3.bat

:: 3. In another terminal, test
test_qwen3.bat
```

## File Structure Changes

```
Ecne-AI-Podcaster/
├── functions/tts/
│   ├── providers/           # NEW: Provider system
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── qwen3.py
│   │   └── orpheus.py
│   ├── api.py              # MODIFIED: Added provider support
│   └── args.py             # MODIFIED: New CLI arguments
├── settings/voices/
│   ├── ryan.yaml           # NEW: Qwen3 voice
│   ├── aiden.yaml          # NEW: Qwen3 voice
│   ├── serena.yaml         # NEW: Qwen3 voice
│   ├── vivian.yaml         # NEW: Qwen3 voice
│   └── ...                 # NEW: Other Qwen3 voices
├── setup_qwen3.sh          # NEW: Linux setup script
├── setup_qwen3.bat         # NEW: Windows setup script
├── requirements_qwen3.txt  # NEW: Qwen3 dependencies
└── QwenTTS_Plan.md         # NEW: Original plan document
```

## API Compatibility

Both providers use OpenAI-compatible endpoints:

- **Qwen3**: `POST http://localhost:8000/v1/audio/speech`
- **Orpheus**: `POST http://localhost:5005/v1/audio/speech`

This makes switching between providers seamless.

## Troubleshooting

### Qwen3 API not responding

```bash
# Check if Qwen3 server is running
curl http://localhost:8000/health

# Start the server
cd EcneAI-Qwen-3-TTS-api && source venv/bin/activate && python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

### Model download issues

```bash
# Models auto-download on first use
# Ensure you have ~4GB free disk space
# Check HuggingFace token if required: export HF_TOKEN=your_token
```

### Switch back to Orpheus

```bash
# Option 1: Use CLI argument
python script_builder.py --script podcast.txt --tts-provider orpheus

# Option 2: Update .env
echo 'TTS_PROVIDER="orpheus"' >> .env
```

## Summary

✅ Qwen3 TTS is now the default provider  
✅ Orpheus TTS remains available as fallback  
✅ Full backward compatibility maintained  
✅ Voice cloning support added  
✅ Emotion control available (Qwen3)  
✅ Setup scripts for easy installation  
✅ Comprehensive voice configuration files  

The integration provides higher quality TTS with more voice options while preserving all existing functionality.
