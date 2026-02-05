"""
Qwen3 TTS Provider implementation.

Integrates with the EcneAI-Qwen-3-TTS-api service for high-quality
text-to-speech with voice cloning and preset speakers.
"""

import time
import requests
from typing import List, Optional, Tuple, Dict, Any

from .base import TTSProvider, TTSVoice, TTSGenerationResult


# Preset speakers available in Qwen3 TTS
QWEN3_PRESET_SPEAKERS = {
    "Vivian": {"language": "Chinese", "gender": "Female", 
               "description": "Bright, Sharp, Young Female"},
    "Serena": {"language": "Chinese", "gender": "Female",
               "description": "Warm, Soft, Young Female"},
    "Uncle_Fu": {"language": "Chinese", "gender": "Male",
                 "description": "Deep, Mellow, Mature Male"},
    "Dylan": {"language": "Chinese", "gender": "Male",
              "description": "Beijing accent, Clear, Natural Young Male"},
    "Eric": {"language": "Chinese", "gender": "Male",
             "description": "Sichuan accent, Lively, Husky Male"},
    "Ryan": {"language": "English", "gender": "Male",
             "description": "Rhythmic, Dynamic Male"},
    "Aiden": {"language": "English", "gender": "Male",
              "description": "Sunny, Clear American Male"},
    "Ono_Anna": {"language": "Japanese", "gender": "Female",
                 "description": "Light, Playful Female"},
    "Sohee": {"language": "Korean", "gender": "Female",
              "description": "Emotional, Warm Female"},
}

# Available models
QWEN3_MODELS = {
    "qwen3-tts-1.7b-base": "Base model for voice cloning",
    "qwen3-tts-1.7b-customvoice": "Model with preset speakers",
}

# Emotion/style instructions
QWEN3_INSTRUCTIONS = [
    "happy", "excited", "angry", "sad", "gentle",
    "fearful", "cold", "whisper", "surprised", "disgusted", "neutral",
    "开心", "激动", "生气", "难过", "温柔", "恐惧", "冷酷", "低语", "惊讶", "厌恶", "平静"
]


class Qwen3Provider(TTSProvider):
    """
    Qwen3 TTS Provider.
    
    Supports:
    - 9 preset speakers in multiple languages
    - Voice cloning from audio samples
    - Emotion/style control
    - Speed adjustment (0.5x - 2.0x)
    """
    
    def __init__(self, api_host: str = "127.0.0.1", api_port: int = 8000, 
                 model: str = "qwen3-tts-1.7b-customvoice", **kwargs):
        """
        Initialize Qwen3 TTS provider.
        
        Args:
            api_host: Hostname of the Qwen3 TTS API
            api_port: Port of the Qwen3 TTS API (default: 8000)
            model: Model to use for synthesis
        """
        super().__init__(api_host, api_port, **kwargs)
        self.model = model
        
    @property
    def name(self) -> str:
        return "qwen3"
    
    @property
    def default_model(self) -> str:
        return "qwen3-tts-1.7b-customvoice"
    
    def get_available_voices(self) -> List[TTSVoice]:
        """Get all preset speakers."""
        voices = []
        for voice_id, info in QWEN3_PRESET_SPEAKERS.items():
            voices.append(TTSVoice(
                id=voice_id,
                name=voice_id,
                language=info["language"],
                gender=info["gender"],
                description=info["description"],
                is_cloned=False
            ))
        return voices
    
    def validate_voice(self, voice_id: str) -> bool:
        """Check if voice is a valid preset speaker or cloned voice ID."""
        if not voice_id:
            return False
        # Check preset speakers
        if voice_id in QWEN3_PRESET_SPEAKERS:
            return True
        # Could also be a cloned voice ID (format: voice_xxxxxx)
        if voice_id.startswith("voice_"):
            return True
        return False
    
    def check_health(self) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Check Qwen3 TTS API health and model status.
        
        Returns:
            Tuple of (is_healthy, message, health_data)
        """
        try:
            response = requests.get(f"{self.base_url}/health", timeout=10)
            if response.status_code != 200:
                return False, f"Health check failed: HTTP {response.status_code}", {}
            
            data = response.json()
            models_loaded = data.get('models_loaded', [])
            device = data.get('device', 'unknown')
            
            # Check model status to see what's available
            try:
                status_response = requests.get(f"{self.base_url}/v1/models/status", timeout=10)
                if status_response.status_code == 200:
                    model_statuses = status_response.json()
                    downloaded_models = [m["model_id"] for m in model_statuses if m.get("downloaded")]
                    not_downloaded = [m["model_id"] for m in model_statuses if not m.get("downloaded")]
                    
                    # Check which models we need
                    required_models = []
                    if self.model == "qwen3-tts-1.7b-customvoice":
                        required_models = ["qwen3-tts-1.7b-customvoice"]
                    elif self.model == "qwen3-tts-1.7b-base":
                        required_models = ["qwen3-tts-1.7b-base"]
                    else:
                        required_models = [self.model]
                    
                    missing_downloaded = [m for m in required_models if m not in downloaded_models]
                    
                    if missing_downloaded:
                        msg = (f"Models need download: {', '.join(missing_downloaded)}. "
                               f"Use: POST {self.base_url}/v1/models/<model_id>/load")
                        return False, msg, data
                    
                    if not_downloaded:
                        msg = (f"API healthy on {device}. Loaded: {models_loaded}. "
                               f"Available for use: {downloaded_models}")
                        return True, msg, data
                    else:
                        return True, f"API healthy on {device}. All models ready", data
                else:
                    # Fallback to basic health check
                    missing_models = [m for m in required_models if m not in models_loaded]
                    if missing_models:
                        return False, f"Models not loaded: {', '.join(missing_models)}", data
                    return True, f"API healthy on {device}. Models loaded: {', '.join(models_loaded)}", data
            except:
                # Fallback to basic health check
                missing_models = [m for m in required_models if m not in models_loaded]
                if missing_models:
                    return False, f"Models not loaded: {', '.join(missing_models)}", data
                return True, f"API healthy on {device}. Models loaded: {', '.join(models_loaded)}", data
                
        except requests.exceptions.ConnectionError:
            return False, "Cannot connect to Qwen3 TTS API. Is it running?", {}
        except Exception as e:
            return False, f"Health check error: {e}", {}
    
    def generate_audio(
        self,
        text: str,
        voice: str,
        speed: float = 1.0,
        output_format: str = "wav",
        max_retries: int = 3,
        timeout: int = 180,
        instructions: Optional[str] = None,
        **kwargs
    ) -> Tuple[Optional[bytes], Optional[int]]:
        """
        Generate audio using Qwen3 TTS API.
        
        Args:
            text: Text to synthesize (max 5000 chars)
            voice: Voice ID (preset speaker or cloned voice)
            speed: Speech speed (0.5 to 2.0)
            output_format: Output format (wav, mp3, ogg, opus)
            max_retries: Number of retry attempts
            timeout: Request timeout in seconds
            instructions: Emotion/style instruction (happy, sad, whisper, etc.)
            
        Returns:
            Tuple of (audio_data_bytes, sample_rate) or (None, None)
        """
        # Check API health first (only once per session, cache the result)
        if not hasattr(self, '_health_checked'):
            is_healthy, message, health_data = self.check_health()
            if not is_healthy:
                print(f"\n!! Qwen3 TTS API Health Check Failed: {message}")
                print(f"!! Please ensure the Qwen3 TTS service is running and models are downloaded.")
                print(f"!! Run: cd EcneAI-Qwen-3-TTS-api && python scripts/download_models.py\n")
                return None, None
            else:
                print(f"\n✅ Qwen3 TTS: {message}")
            self._health_checked = True
        
        # Ensure voice is valid
        if not self.validate_voice(voice):
            print(f"!! Warning: '{voice}' is not a known Qwen3 voice, attempting anyway")
        
        # Prepare request payload
        api_url = f"{self.base_url}/v1/audio/speech"
        
        # Use form data (multipart) as the API expects
        payload = {
            "model": self.model if voice in QWEN3_PRESET_SPEAKERS else "qwen3-tts-1.7b-base",
            "input": text,
            "voice": voice,
            "response_format": output_format.lower(),
            "speed": max(0.5, min(2.0, speed)),  # Clamp to valid range
        }
        
        # Add optional instructions if provided
        if instructions and instructions.lower() in [i.lower() for i in QWEN3_INSTRUCTIONS]:
            payload["instructions"] = instructions
        
        headers = {}
        
        print(f"-> Qwen3 TTS: Generating audio for '{voice}' (speed: {speed}x)")
        print(f"   Text: {text[:60]}{'...' if len(text) > 60 else ''}")
        
        # Attempt request with retries
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    wait_time = 2 ** attempt
                    print(f"   Retry attempt {attempt}/{max_retries} in {wait_time}s...")
                    time.sleep(wait_time)
                
                response = requests.post(
                    api_url,
                    data=payload,
                    headers=headers,
                    timeout=timeout
                )
                response.raise_for_status()
                
                audio_data = response.content
                
                if audio_data and len(audio_data) > 44:  # Valid WAV header is 44 bytes
                    print(f"   ✅ SUCCESS: Received {len(audio_data)} bytes")
                    # Qwen3 outputs at 44100 Hz
                    return audio_data, 44100
                else:
                    raise requests.exceptions.RequestException(
                        f"Empty or invalid audio response ({len(audio_data)} bytes)"
                    )
                    
            except requests.exceptions.Timeout:
                print(f"   ❌ Timeout on attempt {attempt + 1}")
                if attempt == max_retries:
                    return None, None
                    
            except requests.exceptions.ConnectionError as e:
                print(f"   ❌ Connection error: {e}")
                if attempt == max_retries:
                    return None, None
                    
            except requests.exceptions.RequestException as e:
                error_detail = ""
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        error_json = e.response.json()
                        error_detail = f" - {error_json.get('detail', error_json)}"
                    except:
                        error_detail = f" - {e.response.text[:200]}"
                print(f"   ❌ Request error on attempt {attempt + 1}: {e}{error_detail}")
                if attempt == max_retries:
                    return None, None
        
        return None, None
    
    def health_check(self) -> bool:
        """Check if Qwen3 TTS API is available."""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            if response.status_code == 200:
                data = response.json()
                return data.get("status") == "healthy"
            return False
        except:
            return False
    
    def clone_voice(
        self,
        name: str,
        audio_file_path: str,
        description: Optional[str] = None,
        sample_text: Optional[str] = None
    ) -> Optional[str]:
        """
        Clone a voice from an audio sample.
        
        Args:
            name: Name for the cloned voice
            audio_file_path: Path to audio sample (3+ seconds)
            description: Optional description
            sample_text: Transcription of sample (improves quality)
            
        Returns:
            Voice ID if successful, None otherwise
        """
        api_url = f"{self.base_url}/v1/voices"
        
        try:
            with open(audio_file_path, 'rb') as f:
                files = {'voice_sample': f}
                data = {'name': name}
                if description:
                    data['description'] = description
                if sample_text:
                    data['voice_sample_text'] = sample_text
                else:
                    # Enable x_vector_only mode when no sample text provided
                    # This allows zero-shot voice cloning without transcript
                    data['x_vector_only'] = 'true'
                
                response = requests.post(api_url, data=data, files=files, timeout=60)
                response.raise_for_status()
                
                result = response.json()
                voice_id = result.get('voice_id')
                print(f"   ✅ Voice cloned successfully: {voice_id}")
                return voice_id
                
        except Exception as e:
            print(f"   ❌ Voice cloning failed: {e}")
            return None
    
    def list_cloned_voices(self) -> List[Dict[str, Any]]:
        """List all cloned voices."""
        try:
            response = requests.get(f"{self.base_url}/v1/voices", timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get('voices', [])
        except Exception as e:
            print(f"   ❌ Failed to list voices: {e}")
            return []
    
    def get_voice_config(self, voice_id: str) -> Dict[str, Any]:
        """
        Get voice-specific configuration for Qwen3 voices.
        
        Qwen3 voices typically need less post-processing since
        the model produces high-quality output.
        """
        base_config = {
            'gain_factor': 1.0,
            'trim_end_ms': 50,  # Light trim for Qwen3
            'nr_level': 0,  # Qwen3 doesn't need noise reduction
            'compress_thresh': 0.5,  # Light compression
            'compress_ratio': 2,
            'norm_frame_len': 10,
            'norm_gauss_size': 3,
            'deesser_freq': 4000,
            'apply_ffmpeg_enhancement': True,
            'apply_deesser': voice_id not in ['Ryan', 'Aiden'],  # Male voices need less de-essing
        }
        
        # Voice-specific tweaks
        if voice_id in ['Ryan', 'Aiden']:
            # Male voices
            base_config['deesser_freq'] = 5000
            base_config['compress_thresh'] = 0.3
        elif voice_id in ['Serena', 'Vivian', 'Sohee']:
            # Female voices
            base_config['deesser_freq'] = 3500
            base_config['compress_thresh'] = 0.4
        
        return base_config
