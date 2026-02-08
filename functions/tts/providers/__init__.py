"""
TTS Providers module for Ecne-AI-Podcaster.

This module provides a unified interface for multiple TTS providers:
- Qwen3 TTS (default): High-quality voice cloning and preset speakers
- Orpheus TTS (legacy): Original TTS provider
"""

from .base import TTSProvider, TTSVoice, TTSGenerationResult
from .qwen3 import Qwen3Provider
from .orpheus import OrpheusProvider

__all__ = [
    'TTSProvider',
    'TTSVoice',
    'TTSGenerationResult',
    'Qwen3Provider',
    'OrpheusProvider',
    'get_provider',
]

# Provider registry
_PROVIDERS = {
    'qwen3': Qwen3Provider,
    'orpheus': OrpheusProvider,
}


def get_provider(provider_name: str, **kwargs) -> TTSProvider:
    """
    Get a TTS provider instance by name.
    
    Args:
        provider_name: Name of the provider ('qwen3' or 'orpheus')
        **kwargs: Provider-specific initialization arguments
        
    Returns:
        TTSProvider instance
        
    Raises:
        ValueError: If provider name is unknown
    """
    provider_name = provider_name.lower()
    if provider_name not in _PROVIDERS:
        raise ValueError(
            f"Unknown TTS provider: '{provider_name}'. "
            f"Available providers: {list(_PROVIDERS.keys())}"
        )
    
    return _PROVIDERS[provider_name](**kwargs)


def list_providers() -> list[str]:
    """Return list of available provider names."""
    return list(_PROVIDERS.keys())
