import argparse
import os

# Import providers to get available voices
from functions.tts.providers import Qwen3Provider, OrpheusProvider

# Define Voices for both providers
QWEN3_VOICES = [v.id for v in Qwen3Provider().get_available_voices()]
ORPHEUS_VOICES = [v.id for v in OrpheusProvider().get_available_voices()]

# Legacy mapping for backward compatibility
LANGUAGES_VOICES = {
    'English': ['tara', 'leah', 'jess', 'leo', 'dan', 'mia', 'zac', 'zoe'],
    'French': ['pierre', 'amelie', 'marie'],
    'German': ['jana', 'thomas', 'max'],
    'Korean': ['유나', '준서'],
    'Hindi': ['ऋतिका'],
    'Mandarin': ['长乐', '白芷'],
    'Spanish': ['javi', 'sergio', 'maria'],
    'Italian': ['pietro', 'giulia', 'carlo']
}
LANGUAGES = list(LANGUAGES_VOICES.keys())
ALL_VOICES = QWEN3_VOICES + ORPHEUS_VOICES

# Default voices based on character profiles
DEFAULT_QWEN3_HOST_VOICE = 'Ryan'
DEFAULT_QWEN3_GUEST_VOICE = 'Serena'
DEFAULT_ORPHEUS_HOST_VOICE = 'leo'
DEFAULT_ORPHEUS_GUEST_VOICE = 'tara'


def parse_tts_arguments():
    """
    Parses command-line arguments specific to the TTS builder.
    
    Supports both Qwen3 TTS (default) and Orpheus TTS providers.
    """
    parser = argparse.ArgumentParser(
        description="Generate speech from text or a script file using Qwen3 or Orpheus TTS.",
        epilog="Examples:\n"
               "  Qwen3 (default): python3 tts_builder.py --script podcast.txt --host-voice Ryan --guest-voice Serena\n"
               "  Orpheus:         python3 tts_builder.py --script podcast.txt --tts-provider orpheus --host-voice leo --guest-voice tara\n"
               "  Dev Mode:        python3 tts_builder.py --script podcast.txt --dev --output dev_test.wav\n"
               "  Voice Cloning:   python3 tts_builder.py --script podcast.txt --host-voice Ryan --guest-voice voice_abc123",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # --- TTS Provider Selection (NEW) ---
    provider_group = parser.add_argument_group('TTS Provider Selection')
    provider_group.add_argument('--tts-provider', type=str, default='qwen3',
                                choices=['qwen3', 'orpheus'],
                                help='TTS provider to use (default: qwen3). Qwen3 offers higher quality and voice cloning.')
    provider_group.add_argument('--qwen3-port', type=int, default=8000,
                                help='Port for Qwen3 TTS API server (default: 8000)')
    provider_group.add_argument('--qwen3-model', type=str, default='qwen3-tts-1.7b-customvoice',
                                choices=['qwen3-tts-1.7b-base', 'qwen3-tts-1.7b-customvoice'],
                                help='Qwen3 model to use (default: qwen3-tts-1.7b-customvoice)')
    provider_group.add_argument('--orpheus-port', type=int, default=5005,
                                help='Port for Orpheus TTS API server (default: 5005)')

    # --- Input Arguments (Mutually Exclusive) ---
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--input', type=str, help='Single text input to synthesize.')
    group.add_argument('--script', type=str, help='Path to a script file (.txt) with lines like "Speaker: Dialogue".')
    group.add_argument('--resume-from-json', type=str, help='Path to a podcast JSON file to resume editing.')

    # --- Script Specific Arguments ---
    parser.add_argument('--host-voice', type=str, default=None,
                        help='Voice to use for lines starting with "Host:" (script mode only). '
                             'Default: Ryan (Qwen3) or leo (Orpheus)')
    parser.add_argument('--guest-voice', type=str, default=None,
                        help='Voice to use for lines starting with "Guest:" (script mode only). '
                             'Default: Serena (Qwen3) or tara (Orpheus)')
    parser.add_argument('--silence', type=float, default=1.0,
                        help='Duration of silence in seconds between script lines (default: 1.0). Use 0 to disable.')

    # --- General Arguments ---
    parser.add_argument('--voice', type=str, default=None,
                        help='Voice to use for single --input. '
                             'Default: Ryan (Qwen3) or tara (Orpheus).')
    parser.add_argument('--speed', type=float, default=1.0,
                        help='Speech speed factor (0.5 to 2.0 for Qwen3, 0.5 to 1.5 for Orpheus, default: 1.0).')
    parser.add_argument('--port', type=int, default=None,
                        help='[DEPRECATED] Use --qwen3-port or --orpheus-port instead. '
                             'Port the TTS server is running on.')
    parser.add_argument('--api-host', type=str, default='127.0.0.1',
                        help='Host the TTS server is running on (default: 127.0.0.1).')
    
    # --- Qwen3-Specific Arguments ---
    qwen3_group = parser.add_argument_group('Qwen3 TTS Options')
    qwen3_group.add_argument('--qwen3-instruction', type=str, default=None,
                             choices=['happy', 'excited', 'angry', 'sad', 'gentle',
                                      'fearful', 'cold', 'whisper', 'surprised',
                                      'disgusted', 'neutral'],
                             help='Emotion/style instruction for Qwen3 TTS (optional)')
    qwen3_group.add_argument('--qwen3-temperature', type=float, default=0.9,
                             help='Sampling temperature for Qwen3 (0.1 to 2.0, default: 0.9)')
    
    # --- Voice Cloning Arguments ---
    clone_group = parser.add_argument_group('Voice Cloning Options (Qwen3 only)')
    clone_group.add_argument('--host-voice-sample', type=str, default=None,
                             help='Path to audio file for host voice cloning (MP3/WAV)')
    clone_group.add_argument('--host-voice-text', type=str, default=None,
                             help='Transcript text spoken in host voice sample (optional, improves quality)')
    clone_group.add_argument('--guest-voice-sample', type=str, default=None,
                             help='Path to audio file for guest voice cloning (MP3/WAV)')
    clone_group.add_argument('--guest-voice-text', type=str, default=None,
                             help='Transcript text spoken in guest voice sample (optional, improves quality)')
    parser.add_argument('--output', type=str, default='output_speech.wav',
                        help='Output filename for the generated audio (default: output_speech.wav).')
    parser.add_argument('--dev', action='store_true',
                        help='Enable development mode: launch GUI to review/redo segments before finalizing.')
    parser.add_argument('--guest-breakup', action='store_true',
                        help='Break Guest dialogue into sentences for separate TTS processing.')
    parser.add_argument('--tts-max-retries', type=int, default=3,
                        help='Maximum number of retry attempts for failed TTS requests (default: 3).')
    parser.add_argument('--tts-timeout', type=int, default=180,
                        help='Timeout in seconds for each TTS request (default: 180).')

    # --- Video Generation Arguments (used when --dev is enabled) ---
    video_group = parser.add_argument_group('Video Generation Options (--dev mode only)')
    video_group.add_argument('--video-resolution', type=str, default="1280x720",
                             help='Video resolution (e.g., "1920x1080"). Default determined by first background, fallback to this.')
    video_group.add_argument('--video-fps', type=int, default=24,
                             help='Frames per second for the output video.')
    video_group.add_argument('--video-character-scale', type=float, default=1.0,
                              help='Scale factor for character images in the video.')
    video_group.add_argument('--video-fade', type=float, default=1.0,
                              help='Video fade duration for intro/outro segments.')
    video_group.add_argument('--video-intermediate-preset', default='medium',
                             help='Encoding preset for intermediate video segments (e.g., ultrafast, medium, slow).')
    video_group.add_argument('--video-intermediate-crf', type=int, default=23,
                             help='CRF value for intermediate video segments (0-51, lower is better quality).')
    video_group.add_argument('--video-final-audio-bitrate', default='192k',
                             help='Bitrate for final AAC audio encoding (e.g., 128k, 192k).')
    video_group.add_argument('--video-workers', type=int, default=None,
                             help='Number of worker processes for video generation. Defaults to CPU count.')
    video_group.add_argument('--video-keep-temp', action='store_true',
                             help='Keep temporary video segment files after completion.')

    args = parser.parse_args()
    
    # --- Post-processing: Set defaults based on provider ---
    provider = args.tts_provider.lower()
    
    # Determine port based on provider if not explicitly set
    if args.port is not None:
        # Legacy --port argument was used, map it appropriately
        if provider == 'qwen3':
            args.qwen3_port = args.port
        else:
            args.orpheus_port = args.port
    
    # Set default voices based on provider
    if args.host_voice is None:
        args.host_voice = DEFAULT_QWEN3_HOST_VOICE if provider == 'qwen3' else DEFAULT_ORPHEUS_HOST_VOICE
    
    if args.guest_voice is None:
        args.guest_voice = DEFAULT_QWEN3_GUEST_VOICE if provider == 'qwen3' else DEFAULT_ORPHEUS_GUEST_VOICE
    
    if args.voice is None:
        args.voice = DEFAULT_QWEN3_HOST_VOICE if provider == 'qwen3' else DEFAULT_ORPHEUS_GUEST_VOICE
    
    return args


if __name__ == '__main__':
    args = parse_tts_arguments()
    print("Parsed Arguments:")
    for arg, value in vars(args).items():
        print(f"  {arg}: {value}")