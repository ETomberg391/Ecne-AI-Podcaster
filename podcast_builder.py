import argparse
import os
import re
import tempfile
import sys
import json
import shutil # For copying files and rmtree
import datetime

# Import modular functions and classes
from functions.tts.api import generate_audio_segment
from functions.tts.utils import generate_silence, concatenate_wavs
from functions.tts.args import parse_tts_arguments
from functions.tts.gui.main_window import dev_mode_process # Import dev_mode_process
from functions.generate_podcast_video import main as generate_video # Import video generation
import requests

def clone_voice_for_podcast(api_host, api_port, voice_sample_path, voice_sample_text=None, voice_name="Cloned Voice"):
    """
    Clone a voice using the Qwen3 TTS API.
    Returns the voice_id for the cloned voice.
    """
    try:
        api_url = f"http://{api_host}:{api_port}"
        
        # Prepare the request
        with open(voice_sample_path, 'rb') as f:
            files = {'voice_sample': f}
            data = {'name': voice_name}
            if voice_sample_text:
                data['voice_sample_text'] = voice_sample_text
            
            print(f"  -> Cloning voice from {voice_sample_path}...")
            response = requests.post(
                f"{api_url}/v1/voices",
                files=files,
                data=data,
                timeout=60
            )
        
        if response.status_code == 201:
            result = response.json()
            voice_id = result.get('voice_id')
            print(f"  ✅ Voice cloned successfully! Voice ID: {voice_id}")
            return voice_id
        else:
            print(f"  ❌ Failed to clone voice: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"  ❌ Error cloning voice: {e}")
        return None

# Constants
OUTPUT_DIR = "outputs"
TEMP_AUDIO_DIR = "temp_audio"
FINAL_AUDIO_OUTPUT_DIR = os.path.join(OUTPUT_DIR, "final")
ARCHIVE_DIR = os.path.join(OUTPUT_DIR, "archive")

def detect_single_speaker_script(script_path):
    """
    Detects if a script file contains only Host speakers (single speaker mode).
    Returns True if only Host lines are found, False if Guest lines are also present.
    """
    try:
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for Host and Guest lines
        has_host = bool(re.search(r'^Host:', content, re.MULTILINE))
        has_guest = bool(re.search(r'^Guest:', content, re.MULTILINE))
        
        # Single speaker if has Host but no Guest
        return has_host and not has_guest
    except Exception as e:
        print(f"!! Error reading script file {script_path}: {e}")
        return False

def main():
    args = parse_tts_arguments()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(TEMP_AUDIO_DIR, exist_ok=True)
    os.makedirs(FINAL_AUDIO_OUTPUT_DIR, exist_ok=True)
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    temp_dir = TEMP_AUDIO_DIR
    print(f"Using temporary audio directory: {temp_dir}")
    print(f"Saving final outputs to: {OUTPUT_DIR}")

    all_segment_files = []
    reviewable_indices = []
    text_segments_for_dev = []
    success = False
    target_sr = None
    dev_mode_process_result = None # To be accessible in the wider scope

    # Check Qwen3 API health before proceeding
    if args.tts_provider == 'qwen3' or args.tts_provider is None:
        from functions.tts.providers import Qwen3Provider
        api_port = args.qwen3_port if hasattr(args, 'qwen3_port') else (args.port if hasattr(args, 'port') else 8000)
        
        provider = Qwen3Provider(api_host=args.api_host, api_port=api_port)
        is_healthy, message, health_data = provider.check_health()
        
        if not is_healthy:
            print("\n" + "="*60)
            print("QWEN3 TTS API NOT READY")
            print("="*60)
            print(f"Status: {message}")
            print("\nTo fix this:")
            print("1. Ensure Qwen3 TTS service is running:")
            print("   ./start_qwen3.sh")
            print("\n2. Download required models:")
            models_needed = []
            if hasattr(args, 'host_voice_sample') and args.host_voice_sample:
                models_needed.append("qwen3-tts-1.7b-base (for voice cloning)")
            else:
                models_needed.append("qwen3-tts-1.7b-customvoice (for preset voices)")
            if hasattr(args, 'guest_voice_sample') and args.guest_voice_sample:
                models_needed.append("qwen3-tts-1.7b-base (for voice cloning)")
            
            for model in set(models_needed):
                print(f"   python EcneAI-Qwen-3-TTS-api/scripts/download_models.py --model {model}")
            print("="*60 + "\n")
            sys.exit(1)
        else:
            print(f"✅ {message}")
    
    # Handle Voice Cloning (if voice samples are provided)
    if args.tts_provider == 'qwen3' or args.tts_provider is None:
        # Clone Host Voice if sample provided
        if hasattr(args, 'host_voice_sample') and args.host_voice_sample:
            print("\n=== Cloning Host Voice ===")
            cloned_host_id = clone_voice_for_podcast(
                args.api_host, api_port,
                args.host_voice_sample,
                args.host_voice_text if hasattr(args, 'host_voice_text') else None,
                "Host Voice"
            )
            if cloned_host_id:
                args.host_voice = cloned_host_id
                print(f"   Host voice set to cloned ID: {cloned_host_id}")
            else:
                print("   ⚠️  Failed to clone host voice, using preset voice instead")
        
        # Clone Guest Voice if sample provided
        if hasattr(args, 'guest_voice_sample') and args.guest_voice_sample:
            print("\n=== Cloning Guest Voice ===")
            cloned_guest_id = clone_voice_for_podcast(
                args.api_host, api_port,
                args.guest_voice_sample,
                args.guest_voice_text if hasattr(args, 'guest_voice_text') else None,
                "Guest Voice"
            )
            if cloned_guest_id:
                args.guest_voice = cloned_guest_id
                print(f"   Guest voice set to cloned ID: {cloned_guest_id}")
            else:
                print("   ⚠️  Failed to clone guest voice, using preset voice instead")
    
    try:
        if args.input:
            temp_file, generated_sr = generate_audio_segment(
                args.input, args.voice, args.speed, args.api_host, args.port, temp_dir,
                max_retries=args.tts_max_retries, timeout=args.tts_timeout
            )
            if temp_file:
                current_index = len(all_segment_files)
                all_segment_files.append(temp_file)
                reviewable_indices.append(current_index)
                target_sr = generated_sr
                text_segments_for_dev.append((args.input, args.voice, 0)) # Add 0 padding for single input
                
                if not args.dev:
                    print(f"\nCopying single segment to {FINAL_AUDIO_OUTPUT_DIR}...")
                    try:
                        base_name = os.path.splitext(args.output)[0] if args.output else "output"
                        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                        final_audio_filename = f"{base_name}_{timestamp}.wav"
                        output_path = os.path.join(FINAL_AUDIO_OUTPUT_DIR, final_audio_filename)
                        shutil.copy2(temp_file, output_path)
                        print(f"✅ Audio saved successfully to '{output_path}'")
                        success = True
                    except Exception as e:
                        print(f"!! Error copying temp file {temp_file} to {output_path}: {e}")
            else:
                print("!! CRITICAL ERROR: Failed to generate audio for the input text after all retries.")
                print("!! Please check TTS server status and try again.")
                sys.exit(1)  # Exit with error rather than continuing with no audio

        elif args.resume_from_json:
            if not os.path.exists(args.resume_from_json):
                print(f"!! Error: JSON file not found: {args.resume_from_json}")
                sys.exit(1)
            
            print(f"Resuming podcast from {args.resume_from_json}...")
            with open(args.resume_from_json, 'r') as f:
                resumed_data = json.load(f)

            print("\nEntering development mode to resume editing...")
            dev_mode_process_result, save_only = dev_mode_process(
                [], [], [],
                args.api_host, args.port, args.speed, temp_dir,
                args.host_voice, args.guest_voice,
                resumed_data=resumed_data
            )

        elif args.script:
            if not os.path.exists(args.script):
                print(f"!! Error: Script file not found: {args.script}")
                sys.exit(1)

            # Detect if this is a single speaker script
            is_single_speaker = detect_single_speaker_script(args.script)
            if is_single_speaker:
                print("Detected single speaker script (Host only).")
            else:
                print("Detected two-speaker script (Host and Guest).")

            print("Pre-processing script...")
            parsed_segments = []
            try:
                with open(args.script, 'r', encoding='utf-8') as f:
                    for i, line in enumerate(f):
                        line = line.strip()
                        if not line: continue
                        match = re.match(r"^(Host|Guest):\s*(.*)", line, re.IGNORECASE)
                        if match:
                            speaker = match.group(1).lower()
                            dialogue = match.group(2).strip()
                            if dialogue:
                                parsed_segments.append({
                                    'speaker': speaker,
                                    'dialogue': dialogue,
                                    'original_line_index': i + 1
                                })
                        else:
                             print(f"!! Warning: Skipping line {i+1} - format mismatch: \"{line[:60]}...\"")
            except Exception as read_e:
                print(f"!! Error reading script file {args.script}: {read_e}")
                sys.exit(1)

            if not parsed_segments:
                print("!! Error: No valid 'Speaker: Dialogue' lines found in the script.")
                sys.exit(1)
            print(f"Found {len(parsed_segments)} valid dialogue segments.")

            PADDING_SPEAKER_CHANGE_MS = 750
            PADDING_SAME_SPEAKER_MS = 100

            first_segment_generated = False
            for idx, segment_data in enumerate(parsed_segments):
                speaker = segment_data['speaker']
                dialogue = segment_data['dialogue']
                line_num = segment_data['original_line_index']

                pad_ms = 0
                if idx + 1 < len(parsed_segments):
                    next_speaker = parsed_segments[idx + 1]['speaker']
                    if speaker != next_speaker:
                        pad_ms = PADDING_SPEAKER_CHANGE_MS
                    else:
                        pad_ms = PADDING_SAME_SPEAKER_MS
                    print(f"  Segment {idx+1} (Line {line_num}): Next speaker is '{next_speaker}'. Padding = {pad_ms}ms")
                else:
                    print(f"  Segment {idx+1} (Line {line_num}): Last segment. Padding = 0ms")

                # Guest breakup logic - skip if single speaker mode (no guest)
                if speaker == "guest" and args.guest_breakup and not is_single_speaker:
                    import nltk # Import nltk here as it's only used in this block
                    sentences = [dialogue]
                    try:
                        try: nltk.data.find('tokenizers/punkt')
                        except LookupError:
                            print("NLTK 'punkt' tokenizer not found. Attempting download...")
                            nltk.download('punkt')
                            print("Download complete (if successful).")
                        try: sentences = nltk.sent_tokenize(dialogue)
                        except Exception as tokenize_err:
                             print(f"!! NLTK Error tokenizing line {line_num}: {tokenize_err}. Processing as single segment.")
                             sentences = [dialogue]
                    except Exception as nltk_e:
                        print(f"!! Error with NLTK setup for line {line_num}: {nltk_e}. Processing as single segment.")

                    print(f"-> Breaking Guest line {line_num} into chunks (up to 2 sentences).")
                    num_sub_segments = (len(sentences) + 1) // 2
                    for sub_idx in range(num_sub_segments):
                        sent_idx = sub_idx * 2
                        combined_text = ""
                        if sent_idx < len(sentences):
                            combined_text += sentences[sent_idx].strip()
                        if sent_idx + 1 < len(sentences):
                            if combined_text: combined_text += " "
                            combined_text += sentences[sent_idx + 1].strip()

                        if not combined_text: continue

                        sub_pad_ms = PADDING_SAME_SPEAKER_MS if sub_idx < num_sub_segments - 1 else pad_ms

                        voice = args.guest_voice
                        temp_file, generated_sr = generate_audio_segment(
                            combined_text, voice, args.speed, args.api_host, args.port, temp_dir,
                            pad_end_ms=sub_pad_ms, max_retries=args.tts_max_retries, timeout=args.tts_timeout
                        )

                        if temp_file:
                            if not first_segment_generated:
                                target_sr = generated_sr
                                print(f"--- Target sample rate set to {target_sr} Hz ---")
                                first_segment_generated = True
                            elif generated_sr != target_sr:
                                print(f"!! Warning: Samplerate mismatch ({generated_sr} Hz) for sub-segment {sub_idx+1} of line {line_num}. Skipping.")
                                if os.path.exists(temp_file): os.remove(temp_file)
                                continue

                            current_index = len(all_segment_files)
                            all_segment_files.append(temp_file)
                            reviewable_indices.append(current_index)
                            text_segments_for_dev.append((combined_text, voice, sub_pad_ms))
                        else:
                            print(f"!! CRITICAL ERROR: Failed to generate sub-segment {sub_idx+1} for line {line_num} after all retries.")
                            print(f"!! This will result in an incomplete podcast. Please check TTS server and try again.")
                            print(f"!! Stopping podcast generation to avoid incomplete output.")
                            sys.exit(1)  # Exit with error rather than creating incomplete podcast
                else:
                    # For single speaker mode, always use host voice
                    if is_single_speaker:
                        voice = args.host_voice
                    else:
                        voice = args.host_voice if speaker == "host" else args.guest_voice
                    
                    temp_file, generated_sr = generate_audio_segment(
                        dialogue, voice, args.speed, args.api_host, args.port, temp_dir,
                        pad_end_ms=pad_ms, max_retries=args.tts_max_retries, timeout=args.tts_timeout
                    )

                    if temp_file:
                        if not first_segment_generated:
                            target_sr = generated_sr
                            print(f"--- Target sample rate set to {target_sr} Hz ---")
                            first_segment_generated = True
                        elif generated_sr != target_sr:
                            print(f"!! Warning: Samplerate mismatch ({generated_sr} Hz) for line {line_num}. Skipping segment.")
                            if os.path.exists(temp_file): os.remove(temp_file)
                            continue

                        current_index = len(all_segment_files)
                        all_segment_files.append(temp_file)
                        reviewable_indices.append(current_index)
                        text_segments_for_dev.append((dialogue, voice, pad_ms))
                    else:
                        print(f"!! CRITICAL ERROR: Failed to generate segment for line {line_num} after all retries.")
                        print(f"!! This will result in an incomplete podcast. Please check TTS server and try again.")
                        print(f"!! Stopping podcast generation to avoid incomplete output.")
                        sys.exit(1)  # Exit with error rather than creating incomplete podcast

            if args.dev:
                if reviewable_indices:
                    print("\nEntering development mode for segment review...")
                    dev_mode_process_result, save_only = dev_mode_process(
                        all_segment_files,
                        reviewable_indices,
                        text_segments_for_dev,
                        args.api_host, args.port, args.speed, temp_dir, args.host_voice, args.guest_voice
                    )
                else:
                    print("!! No audio segments were generated to review in development mode.")
                    success = False
            elif all_segment_files:
                # This block handles non-dev-mode script processing
                print("\nDev mode not enabled. Concatenating initial segments...")
                final_audio_filename = f"{os.path.splitext(os.path.basename(args.script))[0]}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
                final_output_path = os.path.join(FINAL_AUDIO_OUTPUT_DIR, final_audio_filename)
                print(f"Saving concatenated audio to: {final_output_path}")
                success = concatenate_wavs(all_segment_files, final_output_path, target_sr)
            else:
                print("!! No audio segments were generated successfully for the script.")

        if dev_mode_process_result is not None:
            print("Development mode finished. Processing final segments...")
            if dev_mode_process_result:
                print(f"Found {len(dev_mode_process_result)} segments with audio and visual details")

                if args.resume_from_json:
                    script_name = os.path.splitext(os.path.basename(args.resume_from_json))[0]
                    podcast_archive_dir = os.path.dirname(args.resume_from_json)
                else:
                    script_name = os.path.splitext(os.path.basename(args.script))[0]
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    podcast_archive_dir = os.path.join(ARCHIVE_DIR, f"podcast_{script_name}_{timestamp}")

                raw_audio_dir = os.path.join(podcast_archive_dir, 'raw')
                os.makedirs(raw_audio_dir, exist_ok=True)
                print(f"Using podcast archive directory: {podcast_archive_dir}")

                print(f"\nProcessing {len(dev_mode_process_result)} segments for final JSON...")
                for idx, segment in enumerate(dev_mode_process_result):
                    original_audio_path = segment.get('audio_path')
                    segment_type = segment.get('type', 'unknown')
                    is_temporary = original_audio_path and os.path.abspath(TEMP_AUDIO_DIR) in os.path.abspath(original_audio_path)
                    if is_temporary and os.path.exists(original_audio_path):
                        try:
                            new_name = os.path.basename(original_audio_path)
                            new_path = os.path.join(raw_audio_dir, new_name)
                            if not os.path.exists(new_path) or os.path.getmtime(original_audio_path) > os.path.getmtime(new_path):
                                shutil.copy2(original_audio_path, new_path)
                            segment['audio_path'] = new_path
                        except Exception as copy_err:
                            print(f"    !! ERROR copying temp file '{original_audio_path}': {copy_err}")

                json_config_path = os.path.join(podcast_archive_dir, f"{script_name}.json")
                with open(json_config_path, 'w') as f:
                    json.dump(dev_mode_process_result, f, indent=2)
                print(f"Saved structured segment details to {json_config_path}")

                if save_only:
                    print("\nSave & Close requested. Skipping video generation.")
                    success = True
                else:
                    print("\nAttempting to generate video from the finalized configuration...")
                    timestamp_for_video = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    video_output_filename = f"{script_name}_{timestamp_for_video}.mp4"
                    video_output_path = os.path.join(FINAL_AUDIO_OUTPUT_DIR, video_output_filename)
                    print(f"Saving video output to: {video_output_path}")

                    video_args = argparse.Namespace(
                        config_json=json_config_path,
                        output_video=video_output_path,
                        character_scale=args.video_character_scale,
                        resolution=args.video_resolution,
                        video_fade=args.video_fade,
                        audio_fadein=5.0,
                        audio_fadeout=5.0,
                        fps=args.video_fps,
                        intermediate_preset=args.video_intermediate_preset,
                        intermediate_crf=args.video_intermediate_crf,
                        final_audio_bitrate=args.video_final_audio_bitrate,
                        workers=args.video_workers,
                        keep_temp_files=args.video_keep_temp,
                        temp_output_dir=podcast_archive_dir
                    )
                    try:
                        generate_video(video_args.config_json, video_args.output_video, video_args)
                        print(f"Video generation process initiated for {video_output_path}.")
                        success = True
                    except Exception as video_e:
                        print(f"!! Error calling generate_podcast_video.main: {video_e}")
                        success = False
            else:
                print("!! Development mode cancelled or failed to initialize. No output generated.")
                success = False
        elif not (args.input or args.script or args.resume_from_json):
             print("!! No input provided. Please specify --input, --script, or --resume-from-json.")

    finally:
        print(f"\nCleaning up temporary audio directory: {TEMP_AUDIO_DIR}...")
        try:
            if os.path.isdir(TEMP_AUDIO_DIR):
                shutil.rmtree(TEMP_AUDIO_DIR)
                print(f"-> Temporary audio directory {TEMP_AUDIO_DIR} removed.")
            else:
                print(f"-> Temporary audio directory {TEMP_AUDIO_DIR} does not exist, skipping removal.")
        except Exception as e:
            print(f"!! Warning: Error cleaning up temporary audio directory {TEMP_AUDIO_DIR}: {e}")

        # Pygame mixer quit is now handled in main_window.py's on_closing or run()
        # if pygame and pygame.mixer.get_init():
        #     print("Quitting pygame mixer...")
        #     pygame.mixer.quit()

        if success:
            print("\nProcessing complete.")
        else:
            print("\nProcessing finished with errors or was cancelled.")
            dev_result_is_none = 'dev_mode_process_result' in locals() and dev_mode_process_result is None
            if not success and (not args.dev or dev_result_is_none):
                 print("Exiting with status 1 due to error or cancellation.")
                 sys.exit(1)

if __name__ == "__main__":
    main()