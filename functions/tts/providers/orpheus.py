"""
Orpheus TTS Provider implementation.

Original TTS provider for the Ecne-AI-Podcaster.
Supports multiple languages and voices.
"""

import time
import requests
from typing import List, Optional, Tuple, Dict, Any

from .base import TTSProvider, TTSVoice, TTSGenerationResult


# Orpheus voices organized by language
ORPHEUS_VOICES = {
    'English': ['tara', 'leah', 'jess', 'leo', 'dan', 'mia', 'zac', 'zoe'],
    'French': ['pierre', 'amelie', 'marie'],
    'German': ['jana', 'thomas', 'max'],
    'Korean': ['유나', '준서'],
    'Hindi': ['ऋतिका'],
    'Mandarin': ['长乐', '白芷'],
    'Spanish': ['javi', 'sergio', 'maria'],
    'Italian': ['pietro', 'giulia', 'carlo']
}

# Voice metadata (gender mapping where known)
ORPHEUS_VOICE_METADATA = {
    'tara': {'gender': 'Female', 'description': 'Young female voice'},
    'leah': {'gender': 'Female', 'description': 'Young female voice'},
    'jess': {'gender': 'Female', 'description': 'Young female voice'},
    'leo': {'gender': 'Male', 'description': 'Young male voice'},
    'dan': {'gender': 'Male', 'description': 'Male voice'},
    'mia': {'gender': 'Female', 'description': 'Female voice'},
    'zac': {'gender': 'Male', 'description': 'Male voice'},
    'zoe': {'gender': 'Female', 'description': 'Female voice'},
    'pierre': {'gender': 'Male', 'description': 'French male'},
    'amelie': {'gender': 'Female', 'description': 'French female'},
    'marie': {'gender': 'Female', 'description': 'French female'},
    'jana': {'gender': 'Female', 'description': 'German female'},
    'thomas': {'gender': 'Male', 'description': 'German male'},
    'max': {'gender': 'Male', 'description': 'German male'},
}


class OrpheusProvider(TTSProvider):
    """
    Orpheus TTS Provider.
    
    Original TTS provider supporting multiple languages.
    Default port: 5005
    """
    
    def __init__(self, api_host: str = "127.0.0.1", api_port: int = 5005, **kwargs):
        """
        Initialize Orpheus TTS provider.
        
        Args:
            api_host: Hostname of the Orpheus TTS API
            api_port: Port of the Orpheus TTS API (default: 5005)
        """
        super().__init__(api_host, api_port, **kwargs)
        
    @property
    def name(self) -> str:
        return "orpheus"
    
    @property
    def default_model(self) -> str:
        return "orpheus"
    
    def get_available_voices(self) -> List[TTSVoice]:
        """Get all available Orpheus voices."""
        voices = []
        for language, voice_list in ORPHEUS_VOICES.items():
            for voice_id in voice_list:
                metadata = ORPHEUS_VOICE_METADATA.get(voice_id, {})
                voices.append(TTSVoice(
                    id=voice_id,
                    name=voice_id,
                    language=language,
                    gender=metadata.get('gender'),
                    description=metadata.get('description', f'{language} voice'),
                    is_cloned=False
                ))
        return voices
    
    def validate_voice(self, voice_id: str) -> bool:
        """Check if voice is a valid Orpheus voice."""
        if not voice_id:
            return False
        all_voices = []
        for voices in ORPHEUS_VOICES.values():
            all_voices.extend(voices)
        return voice_id in all_voices
    
    def generate_audio(
        self,
        text: str,
        voice: str,
        speed: float = 1.0,
        output_format: str = "wav",
        max_retries: int = 3,
        timeout: int = 180,
        **kwargs
    ) -> Tuple[Optional[bytes], Optional[int]]:
        """
        Generate audio using Orpheus TTS API.
        
        Args:
            text: Text to synthesize
            voice: Voice ID (e.g., 'leo', 'tara')
            speed: Speech speed (0.5 to 1.5)
            output_format: Output format (wav)
            max_retries: Number of retry attempts
            timeout: Request timeout in seconds
            
        Returns:
            Tuple of (audio_data_bytes, sample_rate) or (None, None)
        """
        # Ensure voice is valid
        if not self.validate_voice(voice):
            print(f"!! Warning: '{voice}' is not a known Orpheus voice, attempting anyway")
        
        # Prepare request - try OpenAI-compatible endpoint first
        api_url = f"{self.base_url}/v1/audio/speech"
        
        payload = {
            "model": "orpheus",
            "input": text,
            "voice": voice,
            "response_format": output_format.lower(),
            "speed": max(0.5, min(1.5, speed))  # Clamp to valid range
        }
        
        headers = {
            "Content-Type": "application/json"
        }
        
        print(f"-> Orpheus TTS: Generating audio for '{voice}' (speed: {speed}x)")
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
                    json=payload,
                    headers=headers,
                    timeout=timeout
                )
                
                # If OpenAI endpoint fails, try legacy endpoint
                if response.status_code == 404:
                    legacy_url = f"{self.base_url}/speak"
                    legacy_payload = {
                        "text": text,
                        "voice": voice
                    }
                    print(f"   Falling back to legacy endpoint: {legacy_url}")
                    response = requests.post(
                        legacy_url,
                        json=legacy_payload,
                        headers=headers,
                        timeout=timeout
                    )
                
                response.raise_for_status()
                audio_data = response.content
                
                if audio_data and len(audio_data) > 44:  # Valid WAV header
                    print(f"   ✅ SUCCESS: Received {len(audio_data)} bytes")
                    # Orpheus outputs at 24000 Hz
                    return audio_data, 24000
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
                print(f"   ❌ Request error on attempt {attempt + 1}: {e}")
                if attempt == max_retries:
                    return None, None
        
        return None, None
    
    def health_check(self) -> bool:
        """Check if Orpheus TTS API is available."""
        try:
            # Try OpenAI-compatible endpoint first
            response = requests.get(f"{self.base_url}/v1/models", timeout=5)
            if response.status_code == 200:
                return True
            # Try health endpoint
            response = requests.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def get_voice_config(self, voice_id: str) -> Dict[str, Any]:
        """
        Get voice-specific configuration for Orpheus voices.
        
        These are the original voice configs from the existing implementation.
        """
        base_config = {
            'gain_factor': 1.0,
            'trim_end_ms': 120,
            'nr_level': 0,
            'compress_thresh': 1.0,
            'compress_ratio': 1,
            'norm_frame_len': 10,
            'norm_gauss_size': 3,
            'deesser_freq': 3000,
            'apply_ffmpeg_enhancement': True,
            'apply_deesser': True,
        }
        
        # Voice-specific tweaks based on existing configs
        if voice_id == 'leo':
            # Leo config from leo.yaml
            base_config['trim_end_ms'] = 100
            base_config['compress_thresh'] = 0.001
            base_config['deesser_freq'] = 5000
            base_config['apply_deesser'] = False  # Leo doesn't need de-essing
        elif voice_id == 'tara':
            base_config['trim_end_ms'] = 120
            base_config['compress_thresh'] = 0.8
        
        return base_config
