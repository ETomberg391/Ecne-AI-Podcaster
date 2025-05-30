import argparse
import os

# Define Languages and Voices (copied from orpheus_tts.py for now, will be removed if centralized)
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
ALL_VOICES = [voice for lang_voices in LANGUAGES_VOICES.values() for voice in lang_voices]

def parse_tts_arguments():
    """
    Parses command-line arguments specific to the TTS builder.
    """
    parser = argparse.ArgumentParser(
        description="Generate speech from text or a script file using Orpheus TTS FastAPI endpoint.",
        epilog="Examples:\n"
               "  Single sentence: python3 tts_builder.py --input \"Hello there.\" --voice leo --output single\n"
               "  From script:   python3 tts_builder.py --script podcast.txt --host-voice leo --guest-voice tara --output podcast_audio.wav --silence 0.5\n"
               "  Dev Mode:      python3 tts_builder.py --script podcast.txt --dev --output dev_test.wav --silence 0.5\n"
               "  Expanded:      python3 tts_builder.py   --script podcast_script_small.txt   --host-voice leo   --guest-voice tara   --output simple_test_script   --dev   --guest-breakup   --video-resolution \"1920x1080\"   --video-fps 24   --video-intermediate-preset slow   --video-intermediate-crf 18   --video-final-audio-bitrate 320k",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # --- Input Arguments (Mutually Exclusive) ---
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--input', type=str, help='Single text input to synthesize.')
    group.add_argument('--script', type=str, help='Path to a script file (.txt) with lines like "Speaker: Dialogue".')

    # --- Script Specific Arguments ---
    parser.add_argument('--host-voice', type=str, default='leo',
                        help='Voice to use for lines starting with "Host:" (script mode only, default: leo).')
    parser.add_argument('--guest-voice', type=str, default='tara',
                        help='Voice to use for lines starting with "Guest:" (script mode only, default: tara).')
    parser.add_argument('--silence', type=float, default=1.0,
                        help='Duration of silence in seconds between script lines (default: 1.0). Use 0 to disable.')

    # --- General Arguments ---
    parser.add_argument('--voice', type=str, default='tara',
                        help='Voice to use for single --input (default: tara).')
    parser.add_argument('--speed', type=float, default=1.0,
                        help='Speech speed factor (0.5 to 1.5, default: 1.0).')
    parser.add_argument('--port', type=int, default=5005,
                        help='Port the Orpheus-FastAPI server is running on (default: 5005).')
    parser.add_argument('--api-host', type=str, default='127.0.0.1',
                        help='Host the Orpheus-FastAPI server is running on (default: 127.0.0.1).')
    parser.add_argument('--output', type=str, default='output_speech.wav',
                        help='Output filename for the generated audio (default: output_speech.wav).')
    parser.add_argument('--dev', action='store_true',
                        help='Enable development mode: launch GUI to review/redo segments before finalizing.')
    parser.add_argument('--guest-breakup', action='store_true',
                        help='Break Guest dialogue into sentences for separate TTS processing.')

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

    return parser.parse_args()

if __name__ == '__main__':
    args = parse_tts_arguments()
    print("Parsed Arguments:")
    for arg, value in vars(args).items():
        print(f"  {arg}: {value}")