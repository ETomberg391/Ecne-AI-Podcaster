"""
Abstract base class for TTS providers.

Defines the interface that all TTS providers must implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple
import io


@dataclass
class TTSVoice:
    """Represents a voice available for TTS generation."""
    id: str
    name: str
    language: str
    gender: Optional[str] = None
    description: Optional[str] = None
    is_cloned: bool = False
    preview_url: Optional[str] = None


@dataclass
class TTSGenerationResult:
    """Result of a TTS generation request."""
    audio_data: bytes
    sample_rate: int
    format: str
    duration_ms: Optional[int] = None


class TTSProvider(ABC):
    """
    Abstract base class for Text-to-Speech providers.
    
    All TTS providers must implement this interface to be compatible
    with the Ecne-AI-Podcaster audio pipeline.
    """
    
    def __init__(self, api_host: str = "127.0.0.1", api_port: int = 8000, **kwargs):
        """
        Initialize the TTS provider.
        
        Args:
            api_host: Hostname/IP of the TTS API server
            api_port: Port of the TTS API server
            **kwargs: Additional provider-specific options
        """
        self.api_host = api_host
        self.api_port = api_port
        self.base_url = f"http://{api_host}:{api_port}"
        
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the provider name."""
        pass
    
    @property
    @abstractmethod
    def default_model(self) -> str:
        """Return the default model identifier."""
        pass
    
    @abstractmethod
    def get_available_voices(self) -> List[TTSVoice]:
        """
        Get list of available voices from this provider.
        
        Returns:
            List of TTSVoice objects
        """
        pass
    
    @abstractmethod
    def validate_voice(self, voice_id: str) -> bool:
        """
        Check if a voice ID is valid for this provider.
        
        Args:
            voice_id: Voice identifier to validate
            
        Returns:
            True if valid, False otherwise
        """
        pass
    
    @abstractmethod
    def generate_audio(
        self,
        text: str,
        voice: str,
        speed: float = 1.0,
        output_format: str = "wav",
        **kwargs
    ) -> Tuple[Optional[bytes], Optional[int]]:
        """
        Generate audio from text.
        
        Args:
            text: Text to synthesize
            voice: Voice ID to use
            speed: Speech speed factor (0.5 to 2.0)
            output_format: Output audio format (wav, mp3, etc.)
            **kwargs: Provider-specific parameters
            
        Returns:
            Tuple of (audio_data_bytes, sample_rate) or (None, None) on failure
        """
        pass
    
    @abstractmethod
    def health_check(self) -> bool:
        """
        Check if the TTS service is available and healthy.
        
        Returns:
            True if service is healthy, False otherwise
        """
        pass
    
    def get_voice_config(self, voice_id: str) -> Dict[str, Any]:
        """
        Get voice-specific configuration for audio processing.
        
        Args:
            voice_id: Voice identifier
            
        Returns:
            Dictionary of configuration parameters
        """
        # Default configuration - override in subclass if needed
        return {
            'gain_factor': 1.0,
            'trim_end_ms': 0,
            'nr_level': 0,
            'compress_thresh': 1.0,
            'compress_ratio': 1,
            'norm_frame_len': 10,
            'norm_gauss_size': 3,
            'deesser_freq': 3000,
            'apply_ffmpeg_enhancement': True,
            'apply_deesser': True,
        }
    
    def _make_api_request(self, endpoint: str, method: str = "GET", 
                          data: Optional[Dict] = None, 
                          files: Optional[Dict] = None,
                          timeout: int = 180) -> Tuple[bool, Any]:
        """
        Helper method to make API requests.
        
        Args:
            endpoint: API endpoint path (e.g., "/v1/audio/speech")
            method: HTTP method
            data: Request data/payload
            files: Files to upload
            timeout: Request timeout in seconds
            
        Returns:
            Tuple of (success, response_data)
        """
        import requests
        
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method.upper() == "GET":
                response = requests.get(url, timeout=timeout)
            elif method.upper() == "POST":
                if files:
                    response = requests.post(url, data=data, files=files, timeout=timeout)
                else:
                    headers = {"Content-Type": "application/json"}
                    response = requests.post(url, json=data, headers=headers, timeout=timeout)
            else:
                return False, f"Unsupported HTTP method: {method}"
            
            response.raise_for_status()
            return True, response
            
        except requests.exceptions.ConnectionError:
            return False, f"Cannot connect to TTS server at {self.base_url}"
        except requests.exceptions.Timeout:
            return False, f"Request to {url} timed out after {timeout}s"
        except requests.exceptions.RequestException as e:
            return False, f"Request failed: {str(e)}"
