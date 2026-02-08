# Qwen3 TTS Integration Plan for Ecne-AI-Podcaster

## Executive Summary

This plan outlines the integration of the **EcneAI-Qwen-3-TTS-api** service as the **primary/default TTS provider** for the Ecne-AI-Podcaster project, while keeping **OrpheusTTS as a secondary/alternative option**.

---

## Current Architecture Overview

### Existing TTS Implementation (OrpheusTTS)
- **API Client**: [`functions/tts/api.py`](functions/tts/api.py:1) - Makes HTTP requests to TTS server
- **Processing**: [`functions/tts/processing.py`](functions/tts/processing.py:1) - Audio enhancements (FFmpeg, pydub)
- **Arguments**: [`functions/tts/args.py`](functions/tts/args.py:1) - CLI argument parsing
- **Utilities**: [`functions/tts/utils.py`](functions/tts/utils.py:1) - Voice config loading, WAV concatenation
- **Voice Configs**: [`settings/voices/*.yaml`](settings/voices/default.yaml:1) - Per-voice audio processing parameters
- **Default Port**: 5005 (Orpheus-FastAPI)
- **Supported Voices**: tara, leah, jess, leo, dan, mia, zac, zoe (English + other languages)

### Qwen3 TTS API Service (Your Service)
- **Location**: [`EcneAI-Qwen-3-TTS-api/`](EcneAI-Qwen-3-TTS-api/)
- **Framework**: FastAPI with OpenAI-compatible endpoints
- **Default Port**: 8000
- **Preset Speakers**: Vivian, Serena, Uncle_Fu, Dylan, Eric, Ryan, Aiden, Ono_Anna, Sohee
- **Models**: qwen3-tts-1.7b-base, qwen3-tts-1.7b-customvoice
- **Features**: Voice cloning, emotion control, multiple output formats

---

## Integration Strategy

### 1. TTS Provider Abstraction Layer

**Goal**: Create a unified interface that supports both TTS providers without breaking existing functionality.

**Implementation**:
- Add `--tts-provider` argument (`qwen3` or `orpheus`, default: `qwen3`)
- Add `--qwen3-port` argument (default: 8000)
- Create provider-specific voice mappings
- Maintain backward compatibility with existing OrpheusTTS setup

### 2. Requirements Integration

**Current [`requirements_host.txt`](requirements_host.txt:1)**:
```
requests, PyYAML, python-dotenv, beautifulsoup4, newspaper4k, PyPDF2,
python-docx, selenium, soundfile, numpy, Pillow, nltk, pydub, matplotlib,
scipy, pygame, lxml_html_clean, flask, moviepy==1.0.3
```

**Qwen3 TTS Requirements** ([`EcneAI-Qwen-3-TTS-api/requirements.txt`](EcneAI-Qwen-3-TTS-api/requirements.txt:1)):
- Core: `torch>=2.0.0,<2.6.0`, `torchaudio`, `transformers==4.57.3`, `qwen-tts==0.0.5`
- API: `fastapi>=0.104.0`, `uvicorn[standard]>=0.24.0`
- Audio: `librosa>=0.10.1`, `ffmpeg-python`, `sox`
- ML: `accelerate>=0.25.0`, `einops`, `onnxruntime`

**Approach**:
- Keep `requirements_host.txt` as the **Podcaster app requirements** (lightweight)
- Add conditional installation for Qwen3 TTS service
- Create separate `requirements_qwen3.txt` for the embedded service

### 3. Voice Configuration Mapping

**OrpheusTTS Voices** (Current):
```python
LANGUAGES_VOICES = {
    'English': ['tara', 'leah', 'jess', 'leo', 'dan', 'mia', 'zac', 'zoe'],
    'French': ['pierre', 'amelie', 'marie'],
    # ... other languages
}
```

**Qwen3 TTS Preset Speakers** ([`EcneAI-Qwen-3-TTS-api/api/config.py`](EcneAI-Qwen-3-TTS-api/api/config.py:137)):
```python
PRESET_SPEAKERS = {
    "Vivian": "Chinese - Bright, Sharp, Young Female",
    "Serena": "Chinese - Warm, Soft, Young Female",
    "Uncle_Fu": "Chinese - Deep, Mellow, Mature Male",
    "Dylan": "Chinese Beijing - Clear, Natural Young Male",
    "Eric": "Chinese Sichuan - Lively, Husky Male",
    "Ryan": "English - Rhythmic, Dynamic Male",
    "Aiden": "English - Sunny, Clear American Male",
    "Ono_Anna": "Japanese - Light, Playful Female",
    "Sohee": "Korean - Emotional, Warm Female",
}
```

**Recommendation**:
- Map host/guest roles to appropriate Qwen3 voices
- Create new voice config files for Qwen3 preset speakers
- Suggested mapping:
  - **Host (Male)**: `Ryan` or `Aiden` (English)
  - **Guest (Female)**: `Serena` or `Vivian` (can be cloned for English)

### 4. API Compatibility

**OrpheusTTS Endpoint**:
```
POST /v1/audio/speech
{
  "model": "orpheus",
  "input": "text",
  "voice": "leo",
  "response_format": "wav",
  "speed": 1.0
}
```

**Qwen3 TTS Endpoint** ([`EcneAI-Qwen-3-TTS-api/api/routes/tts.py`](EcneAI-Qwen-3-TTS-api/api/routes/tts.py:20)):
```
POST /v1/audio/speech
{
  "model": "qwen3-tts-1.7b-customvoice",
  "input": "text",
  "voice": "Ryan",
  "response_format": "wav",
  "speed": 1.0,
  "instructions": "happy"  # Optional emotion
}
```

**Compatibility**: ✅ Both use OpenAI-compatible endpoints - minimal changes needed!

### 5. File Structure Changes

```
Ecne-AI-Podcaster/
├── functions/tts/
│   ├── __init__.py
│   ├── api.py                    # Modified: Add provider selection
│   ├── args.py                   # Modified: Add --tts-provider, --qwen3-port
│   ├── processing.py             # Unchanged (reusable)
│   ├── utils.py                  # Modified: Add provider-specific config loading
│   └── providers/                # NEW: Provider-specific modules
│       ├── __init__.py
│       ├── base.py               # NEW: Abstract base class
│       ├── orpheus.py            # NEW: OrpheusTTS provider
│       └── qwen3.py              # NEW: Qwen3 TTS provider
├── settings/voices/
│   ├── default.yaml
│   ├── leo.yaml
│   ├── tara.yaml
│   ├── ryan.yaml                 # NEW: Qwen3 Ryan voice config
│   ├── aiden.yaml                # NEW: Qwen3 Aiden voice config
│   ├── serena.yaml               # NEW: Qwen3 Serena voice config
│   └── vivian.yaml               # NEW: Qwen3 Vivian voice config
├── EcneAI-Qwen-3-TTS-api/        # EXISTING: Your service
├── requirements_host.txt         # Modified: Keep lightweight
├── requirements_qwen3.txt        # NEW: Qwen3 service requirements
├── Installer_Linux.sh            # Modified: Add Qwen3 setup option
├── Installer_Windows.bat         # Modified: Add Qwen3 setup option
└── QwenTTS_Plan.md               # This file
```

---

## Implementation Steps

### Phase 1: Requirements & Setup

1. **Create `requirements_qwen3.txt`**
   - Extract Qwen3-specific dependencies
   - Exclude duplicates already in `requirements_host.txt`

2. **Modify Installers**
   - Add option to install/setup Qwen3 TTS service
   - Add `--setup-qwen3` flag to installers
   - Handle git submodule/setup for `EcneAI-Qwen-3-TTS-api/`

3. **Create `.env` Template Updates**
   - Add `TTS_PROVIDER=qwen3` (default)
   - Add `QWEN3_API_PORT=8000`
   - Keep `ORPHEUS_API_PORT=5005`

### Phase 2: Code Refactoring

1. **Create Provider Abstraction** (`functions/tts/providers/`)
   ```python
   # base.py - Abstract base class
   class TTSProvider(ABC):
       @abstractmethod
       def generate_audio(self, text, voice, speed, **kwargs): ...
       
       @abstractmethod
       def get_available_voices(self): ...
       
       @abstractmethod
       def validate_voice(self, voice): ...
   ```

2. **Implement Qwen3 Provider** (`functions/tts/providers/qwen3.py`)
   - Wrap API calls to local Qwen3 service
   - Handle preset speaker selection
   - Support voice cloning features

3. **Implement Orpheus Provider** (`functions/tts/providers/orpheus.py`)
   - Move existing Orpheus logic here
   - Maintain backward compatibility

4. **Modify `functions/tts/api.py`**
   - Add provider selection logic
   - Route calls to appropriate provider
   - Maintain existing retry/error handling

5. **Modify `functions/tts/args.py`**
   ```python
   parser.add_argument('--tts-provider', type=str, default='qwen3',
                       choices=['qwen3', 'orpheus'],
                       help='TTS provider to use (default: qwen3)')
   parser.add_argument('--qwen3-port', type=int, default=8000,
                       help='Port for Qwen3 TTS API (default: 8000)')
   parser.add_argument('--qwen3-model', type=str, 
                       default='qwen3-tts-1.7b-customvoice',
                       choices=['qwen3-tts-1.7b-base', 
                                'qwen3-tts-1.7b-customvoice'],
                       help='Qwen3 model to use')
   ```

6. **Create Voice Configs for Qwen3**
   - `settings/voices/ryan.yaml` - For host
   - `settings/voices/aiden.yaml` - Alternative host
   - `settings/voices/serena.yaml` - For guest
   - `settings/voices/vivian.yaml` - Alternative guest

### Phase 3: Integration & Testing

1. **Update Character Profiles**
   - Modify `settings/characters/host.yml` to reference Qwen3 voice
   - Modify `settings/characters/guest.yml` to reference Qwen3 voice

2. **Service Management**
   - Add startup script to launch Qwen3 service if selected
   - Health check integration
   - Auto-fallback to Orpheus if Qwen3 unavailable

3. **Testing Matrix**
   - Test Qwen3 with preset speakers
   - Test voice cloning workflow
   - Test fallback to Orpheus
   - Test audio processing pipeline (FFmpeg/pydub)

### Phase 4: Documentation

1. **Update README.md**
   - Add Qwen3 TTS as primary option
   - Document voice selection
   - Document voice cloning capabilities

2. **Update installation_readme.md**
   - Add Qwen3 setup instructions
   - Document GPU requirements
   - Document model download (auto on first run)

---

## Technical Considerations

### Model Size & Resources
- **Qwen3 TTS Model**: ~1.7B parameters (~3.5GB download)
- **GPU Recommended**: For real-time synthesis
- **CPU Fallback**: Available but slower
- **Model Cache**: Stored in `EcneAI-Qwen-3-TTS-api/models/`

### Port Configuration
| Service | Default Port | Configurable |
|---------|-------------|--------------|
| Qwen3 TTS | 8000 | `--qwen3-port` |
| Orpheus TTS | 5005 | `--port` (existing) |
| Control Panel | 5000 | (Flask default) |

### Audio Processing Compatibility
- Both services output WAV format ✅
- Existing FFmpeg/pydub processing works for both ✅
- Voice config YAML format remains compatible ✅

### Voice Cloning Workflow
1. User provides voice sample (3+ seconds)
2. Call `POST /v1/voices` to create voice
3. Store returned `voice_id`
4. Use `voice_id` in subsequent TTS requests
5. Optional: Save voice ID to character profile

---

## Migration Guide for Existing Users

### New Installations
```bash
# Linux
./Installer_Linux.sh --setup-qwen3

# Windows
Installer_Windows.bat --setup-qwen3
```

### Existing Users
1. Pull latest changes
2. Run setup for Qwen3:
   ```bash
   cd EcneAI-Qwen-3-TTS-api
   ./install.sh  # or install.bat on Windows
   ```
3. Update `.env`:
   ```
   TTS_PROVIDER=qwen3
   QWEN3_API_PORT=8000
   ```
4. Test with new voices:
   ```bash
   python script_builder.py --script test.txt --host-voice Ryan --guest-voice Serena
   ```

### Backward Compatibility
- Existing `--port` argument still works for Orpheus
- Existing voice configs (leo, tara, etc.) still work with Orpheus
- No breaking changes to existing workflows

---

## Recommended Default Voices

Based on your character profiles:

| Character | Recommended Voice | Rationale |
|-----------|------------------|-----------|
| Eric Dundell (Host) | `Ryan` | English, rhythmic, dynamic - fits tech host |
| Dr. Evelyn Reed (Guest) | `Serena` | Warm, soft - fits knowledgeable expert |

Alternative options:
- Host: `Aiden` (Sunny, clear American male)
- Guest: `Vivian` (Bright, sharp female, may clone to English)

---

## Future Enhancements

1. **Voice Cloning UI**: Add GUI for recording/uploading voice samples
2. **Emotion Control**: Expose `instructions` parameter for emotion (happy, sad, whisper, etc.)
3. **Multi-language Support**: Leverage Qwen3's Chinese/Japanese/Korean voices
4. **Voice Mixing**: Blend multiple cloned voices for unique characters
5. **Cloud Mode**: Option to use cloud Qwen3 API instead of local

---

## Summary

This integration plan enables:
- ✅ Qwen3 TTS as default provider (higher quality, voice cloning)
- ✅ OrpheusTTS as fallback/alternative (backward compatibility)
- ✅ Unified API interface for both providers
- ✅ Minimal breaking changes to existing code
- ✅ Extended voice options (9 preset + cloned voices)
- ✅ Future-proof architecture for additional TTS providers

**Estimated Implementation Time**: 1-2 days
**Risk Level**: Low (OpenAI-compatible APIs, backward compatible)
