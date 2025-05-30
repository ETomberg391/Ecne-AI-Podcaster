import json
import os
import argparse
import numpy as np
from moviepy.editor import (VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip,
                             TextClip, CompositeAudioClip, ColorClip) # Removed concatenate_videoclips
from moviepy.video.fx.all import fadein, fadeout
from moviepy.audio.AudioClip import AudioClip # Import for creating silent audio
from PIL import Image # To get image dimensions if needed
import multiprocessing
from functools import partial
import time # To measure execution time
import tempfile # For temporary segment files
import uuid # For unique filenames
import shutil # For audio copy
import subprocess # For FFmpeg noise reduction AND concatenation
import shlex # For safe command string formatting for printing
# Removed soundfile and noisereduce imports as they weren't used in v3's active code path

# --- Constants ---
HOST_POS = ('left', 'bottom')
GUEST_POS = ('right', 'bottom')
CHARACTER_SCALE = 1.0 # Scale factor for host/guest images (updated by args)
TEXT_FONT = 'Arial' # Example font, adjust as needed
TEXT_FONTSIZE = 24
TEXT_COLOR = 'white'
TEXT_BG_COLOR = 'black' # Optional background for text
FADE_DURATION = 1.0 # Seconds for fade in/out (updated by args)

# --- Helper Functions ---
# (Helper functions resize_image_with_pil, create_image_clip, create_character_clip remain unchanged)
def resize_image_with_pil(image_path, target_size, method=Image.Resampling.LANCZOS):
    """Resizes an image using PIL with a specified method."""
    try:
        img = Image.open(image_path)
        img.thumbnail(target_size, method)
        return img
    except Exception as e:
        print(f"  Error resizing image {image_path} with PIL: {e}")
        return None

def create_image_clip(image_path, duration, screen_size):
    """Creates an ImageClip, resizing using PIL LANCZOS to fit screen_size."""
    try:
        img = Image.open(image_path)
        original_size = img.size
        if img.width > screen_size[0] or img.height > screen_size[1]:
            img.thumbnail(screen_size, Image.Resampling.LANCZOS)
        # Create a copy of the image data for moviepy
        img_array = np.array(img.copy())
        img_clip = ImageClip(img_array, duration=duration)
        img_clip = img_clip.set_position('center')
        img.close() # Close PIL image after use
        return img_clip
    except Exception as e:
        print(f"Error creating image clip for {image_path}: {e}")
        return None

def create_character_clip(image_path, duration, screen_size, position):
    """Creates a scaled and positioned ImageClip for a character using PIL LANCZOS."""
    try:
        img = Image.open(image_path)
        original_size = img.size
        new_size = tuple(int(dim * CHARACTER_SCALE) for dim in img.size)
        img_resized = img.resize(new_size, Image.Resampling.LANCZOS)
         # Create a copy of the image data for moviepy
        char_array = np.array(img_resized.copy())
        char_clip = ImageClip(char_array, duration=duration, transparent=True)
        char_clip = char_clip.set_position(position)
        img.close() # Close PIL image after use
        img_resized.close()
        return char_clip
    except Exception as e:
        print(f"Error creating character clip for {image_path}: {e}")
        return None


# --- Clip Creation Functions (for individual segments) ---
# (create_intro_outro_clip_object remains mostly unchanged)

# MODIFIED: Avoid closing original audio when subclip is taken
def create_speech_segment_clip_object(task_data, screen_size, work_dir, trim_amount=0.0):
    """
    Creates a MoviePy clip object for a single podcast speech segment using task_data.
    Applies noise reduction to audio if applicable.
    Trims audio *before* creating visuals to maintain sync.
    Handles resource cleanup carefully.
    """
    original_audio_path = task_data.get('audio_path')
    speaker = task_data.get('speaker')
    bg_path = task_data.get('bg_image')
    host_path = task_data.get('host_image')
    guest_path = task_data.get('guest_image')
    processed_audio_path = original_audio_path # Start assuming we use the original
    if not original_audio_path or not os.path.exists(original_audio_path):
        print(f"  Warning (Worker): Original audio file missing or invalid: {original_audio_path}. Skipping segment.")
        return None

    # --- Noise Reduction ---
    # (Noise reduction logic using FFmpeg remains unchanged)
    print(f"  [Debug] Checking segment: speaker='{speaker}', audio='{original_audio_path}'")
    if speaker in ['tara', 'leo'] and original_audio_path and original_audio_path.lower().endswith('.wav'):
        cleaned_audio_filename = f"{os.path.splitext(os.path.basename(original_audio_path))[0]}_ffmpeg_cleaned.wav"
        cleaned_audio_filepath = os.path.join(work_dir, cleaned_audio_filename)
        try:
            print(f"  Applying FFmpeg processing (de-ess, NR, norm) to {speaker} audio: {os.path.basename(original_audio_path)}...")
            ffmpeg_command = [
                'ffmpeg',
                '-i', original_audio_path,
                '-af', 'asplit [main][side]; [side] bandpass=f=6000:width_type=h:w=4000 [sidechain]; [main][sidechain] sidechaincompress=threshold=0.03:ratio=12:attack=10:release=100, afftdn=nr=30, dynaudnorm=f=150:g=15',
                '-y', # Overwrite output
                cleaned_audio_filepath
            ]
            print(f"    Attempting to run FFmpeg command: {' '.join(ffmpeg_command)}")
            result = subprocess.run(ffmpeg_command, capture_output=True, text=True, check=False)

            print(f"    FFmpeg process finished.")
            print(f"    Return Code: {result.returncode}")
            if result.stdout: print(f"    FFmpeg stdout:\n{result.stdout.strip()}")
            if result.stderr: print(f"    FFmpeg stderr:\n{result.stderr.strip()}")

            if result.returncode == 0 and os.path.exists(cleaned_audio_filepath) and os.path.getsize(cleaned_audio_filepath) > 0:
                processed_audio_path = cleaned_audio_filepath
                print(f"    -> SUCCESS: Saved FFmpeg cleaned audio to: {cleaned_audio_filename}")
            else:
                print(f"  Warning: FFmpeg processing failed or produced empty file for {original_audio_path}. Using original.")
                processed_audio_path = original_audio_path
        except FileNotFoundError:
            print(f"  Error: 'ffmpeg' command not found. Using original audio.")
            processed_audio_path = original_audio_path
        except Exception as ffmpeg_e:
             print(f"  Warning: Error running FFmpeg processing for {original_audio_path}: {ffmpeg_e}. Using original.")
             processed_audio_path = original_audio_path
    # --- End Noise Reduction ---

    # --- Load and Trim Audio FIRST ---
    audio_clip_to_use = None # This will hold the final audio clip (trimmed or original)
    original_audio_clip = None
    duration = 0
    try:
        original_audio_clip = AudioFileClip(processed_audio_path)
        original_duration = original_audio_clip.duration
        if original_duration <= 0:
             print(f"  Warning: Audio file {processed_audio_path} has zero or negative duration. Skipping.")
             if original_audio_clip: original_audio_clip.close()
             return None

        # Apply trim to audio first if needed
        if trim_amount > 0 and original_duration > trim_amount:
            # Create the trimmed clip
            audio_clip_to_use = original_audio_clip.subclip(0, original_duration - trim_amount)
            duration = audio_clip_to_use.duration
            # *** CHANGE: Do NOT close original_audio_clip here. Let the final clip manage it. ***
            # if original_audio_clip: original_audio_clip.close()
            # original_audio_clip = None # Clear reference
        else:
            # Use the original clip directly
            audio_clip_to_use = original_audio_clip
            duration = original_duration
            # No need to close original_audio_clip here, audio_clip_to_use holds the reference

    except Exception as e:
        print(f"  Error loading/trimming audio {processed_audio_path}: {e}. Skipping segment.")
        # Ensure cleanup if error occurred during loading or trimming
        if original_audio_clip:
            try: original_audio_clip.close()
            except: pass
        # audio_clip_to_use might be the trimmed clip if trimming worked but subsequent access failed
        if audio_clip_to_use and audio_clip_to_use != original_audio_clip: # Check if it's a separate object
             try: audio_clip_to_use.close()
             except: pass
        return None
    # --- End Audio Loading/Trimming ---

    # --- Create Visuals using (potentially trimmed) duration ---
    clips_to_composite = []
    # resources_to_close removed, rely on final_clip.close()
    fallback_bg = None

    # Use 'duration' which now reflects the trimmed audio length
    if bg_path and os.path.exists(bg_path):
        bg_clip = create_image_clip(bg_path, duration, screen_size)
        if bg_clip:
            clips_to_composite.append(bg_clip)
        else:
            print(f"  Warning: Could not create background clip for {bg_path}. Using fallback.")
            fallback_bg = ColorClip(size=screen_size, color=(0,0,0), duration=duration)
            clips_to_composite.append(fallback_bg)
    else:
        fallback_bg = ColorClip(size=screen_size, color=(0,0,0), duration=duration)
        clips_to_composite.append(fallback_bg)

    if host_path and os.path.exists(host_path):
        host_clip = create_character_clip(host_path, duration, screen_size, HOST_POS)
        if host_clip:
            clips_to_composite.append(host_clip)
        else: print(f"  Warning: Could not create host clip for {host_path}")

    if guest_path and os.path.exists(guest_path):
        guest_clip = create_character_clip(guest_path, duration, screen_size, GUEST_POS)
        if guest_clip:
            clips_to_composite.append(guest_clip)
        else: print(f"  Warning: Could not create guest clip for {guest_path}")

    if len(clips_to_composite) == 0:
         print("  Error: No visual elements could be created.")
         if audio_clip_to_use: # Close the audio clip we loaded/trimmed
              try: audio_clip_to_use.close()
              except: pass
         return None
    # --- End Visual Creation ---

    # --- Composite and Finalize ---
    final_clip = None
    try:
        # Ensure audio_clip_to_use is valid before proceeding
        if not audio_clip_to_use:
             print("  Error: Audio clip is invalid before compositing.")
             # Cleanup visuals created so far
             for clip_item in clips_to_composite:
                 try: clip_item.close()
                 except: pass
             return None

        final_clip = CompositeVideoClip(clips_to_composite, size=screen_size, use_bgclip=True if fallback_bg is None else False)
        final_clip = final_clip.set_audio(audio_clip_to_use) # Use the final audio clip
        final_clip.duration = duration # Use the potentially trimmed duration

        # IMPORTANT: Do not close audio_clip_to_use or visual clips here.
        # final_clip now 'owns' them, and final_clip.close() in the worker's finally block will handle it.
        return final_clip

    except Exception as comp_e:
         print(f"  Error during compositing or audio setting for {processed_audio_path}: {comp_e}")
         # Cleanup resources created in this function
         if final_clip:
              # If final_clip exists, closing it should handle attached components
              try: final_clip.close()
              except: pass
         else:
              # If final_clip wasn't created or failed early, close components individually
              if audio_clip_to_use:
                   try: audio_clip_to_use.close()
                   except: pass
              for clip_item in clips_to_composite: # Close visuals if compositing failed
                   try: clip_item.close()
                   except: pass
         return None
    # --- End Compositing ---

def create_intro_outro_clip_object(task_data, screen_size, is_intro=True, args=None):
    """Creates the intro or outro MoviePy clip object using task_data."""
    clip_type = "Intro" if is_intro else "Outro"
    music_path = task_data.get('audio_path') # Might be None
    bg_path = task_data.get('bg_image')
    host_path = task_data.get('host_image')
    guest_path = task_data.get('guest_image')

    audio_clip = None # This will hold the final audio clip for the intro/outro
    audio_clip_temp = None # Temporary holder during loading
    duration = 5.0

    if music_path and os.path.exists(music_path):
        try:
            audio_clip_temp = AudioFileClip(music_path)
            temp_duration = audio_clip_temp.duration
            if temp_duration <= 0:
                 print(f"  Warning: {clip_type} music {music_path} has zero duration. Using default 5s.")
                 audio_clip_temp.close() # Close the invalid temp clip
            else:
                 duration = temp_duration
                 audio_clip = audio_clip_temp # Assign the valid clip
                 audio_clip_temp = None # Clear temp reference
        except Exception as e:
            print(f"  Warning: Could not load {clip_type} music {music_path}: {e}. Using default duration 5s.")
            if audio_clip_temp: # Ensure temp is closed if loading failed
                try: audio_clip_temp.close()
                except: pass
    else:
        print(f"  Info: No music path provided for {clip_type}. Using default duration {duration}s.")
        pass # Use default duration 5s, audio_clip remains None

    clips_to_composite = []
    # resources_to_close removed, rely on final_clip.close()
    print(f"\n[Worker {os.getpid()} Debug] Received task_data:\n{task_data}") # DEBUG WORKER DATA
    fallback_bg = None

    if bg_path and os.path.exists(bg_path):
        bg_clip = create_image_clip(bg_path, duration, screen_size)
        if bg_clip:
            clips_to_composite.append(bg_clip)
        else:
            print(f"  Warning: Could not create {clip_type} background clip for {bg_path}. Using fallback.")
            fallback_bg = ColorClip(size=screen_size, color=(0,0,0), duration=duration)
            clips_to_composite.append(fallback_bg)
    else:
        fallback_bg = ColorClip(size=screen_size, color=(0,0,0), duration=duration)
        clips_to_composite.append(fallback_bg)

    if host_path and os.path.exists(host_path):
        host_clip = create_character_clip(host_path, duration, screen_size, HOST_POS)
        if host_clip:
            clips_to_composite.append(host_clip)
        else: print(f"  Warning: Could not create {clip_type} host clip for {host_path}")

    if guest_path and os.path.exists(guest_path):
        guest_clip = create_character_clip(guest_path, duration, screen_size, GUEST_POS)
        if guest_clip:
            clips_to_composite.append(guest_clip)
        else: print(f"  Warning: Could not create {clip_type} guest clip for {guest_path}")

    if len(clips_to_composite) == 0:
         print(f"  Error: No visual elements could be created for the {clip_type}.")
         if audio_clip: # Close loaded audio if visual failed
             try: audio_clip.close()
             except: pass
         return None

    final_clip = None
    try:
        final_clip = CompositeVideoClip(clips_to_composite, size=screen_size, use_bgclip=True if fallback_bg is None else False)

        if audio_clip: # Check if we have a valid audio clip
            fadeout_duration = args.audio_fadeout if args else 5.0
            fadein_duration = args.audio_fadein if args else 5.0
            fadeout_duration = min(fadeout_duration, duration)
            fadein_duration = min(fadein_duration, duration)

            # Apply fades - this modifies the audio_clip in place or returns a new one
            if is_intro and fadeout_duration > 0: audio_clip = audio_clip.audio_fadeout(fadeout_duration)
            elif not is_intro and fadein_duration > 0: audio_clip = audio_clip.audio_fadein(fadein_duration)

            final_clip = final_clip.set_audio(audio_clip)
        # else: final_clip already has no audio, which is fine

        video_fade_duration = min(FADE_DURATION, duration)
        if video_fade_duration > 0:
            if is_intro: final_clip = fadein(final_clip, video_fade_duration)
            else: final_clip = fadeout(final_clip, video_fade_duration)

        final_clip.duration = duration
        # Do not close audio_clip or visuals here; rely on final_clip.close()
        return final_clip
    except Exception as comp_e:
        print(f"  Error during compositing/fading for {clip_type}: {comp_e}")
        # Cleanup resources created in this function
        if final_clip:
            try: final_clip.close()
            except: pass
        else:
             # If final_clip failed, close components individually
             if audio_clip:
                 try: audio_clip.close()
                 except: pass
             for clip_item in clips_to_composite: # Close visuals
                  try: clip_item.close()
                  except: pass
        return None

# --- Worker Function for Multiprocessing ---
def process_segment_worker(task_data, screen_size, args, temp_dir, work_dir):
    """
    Worker function using task_data dictionary. Creates clip object, writes to temp file.
    Handles creation of speech, intro, or outro segments.
    Returns the path to the generated temporary video file, or None if failed.
    """
    segment_type = task_data['type']
    segment_idx = task_data['index']

    clip = None
    temp_video_path = None
    try:
        if segment_type == 'intro':
            clip = create_intro_outro_clip_object(task_data, screen_size, is_intro=True, args=args)
        elif segment_type == 'speech':
            # Define trim amount here, could also be an arg if needed per-segment type
            trim_amount_worker = 0.12 # This is the necessary trim for audio glitches
            # Pass trim amount to the creation function
            clip = create_speech_segment_clip_object(task_data, screen_size, work_dir, trim_amount=trim_amount_worker)
        elif segment_type == 'outro':
            clip = create_intro_outro_clip_object(task_data, screen_size, is_intro=False, args=args)

        # Check if clip creation was successful before proceeding
        if clip:
            # --- REMOVED: Trimming is now handled inside create_speech_segment_clip_object ---

            # Intermediate encoding params (CPU encoding for temp files, quality controlled by args)
            intermediate_encoding_params = {
                'codec': 'libx264',
                'preset': args.intermediate_preset if args else 'medium', # Use arg for preset
                'fps': args.fps if args else 24,
                'audio_codec': 'pcm_s16le', # Use uncompressed PCM for intermediate audio
                'temp_audiofile': os.path.join(temp_dir, f'temp-audio-worker-{os.getpid()}-{uuid.uuid4()}.wav'), # Changed extension
                'remove_temp': True, 'verbose': False, 'logger': None,
                'threads': 1, # Limit threads for intermediate writes
                'ffmpeg_params': ['-crf', str(args.intermediate_crf if args else 23)] # Use arg for CRF
            }
            temp_filename = f"segment_{segment_idx+1:04d}_{segment_type}_{uuid.uuid4()}.mp4" # Padded index for sorting
            temp_video_path = os.path.join(temp_dir, temp_filename)

            # --- Add Audio Check Before Write ---
            if clip.audio:
                 # This debug log now reflects the duration *after* potential audio trimming
                 print(f"  [Worker {os.getpid()}] DEBUG: Segment {segment_idx+1} audio duration (potentially trimmed) BEFORE write: {clip.audio.duration:.2f}s")
            else:
                 print(f"  [Worker {os.getpid()}] WARNING: Segment {segment_idx+1} has NO AUDIO before writing temp file!")
            # --- End Audio Check ---

            # Write the video file
            clip.write_videofile(temp_video_path, **intermediate_encoding_params)
            print(f"  [Worker {os.getpid()}] Segment {segment_idx+1} ({segment_type}) -> {os.path.basename(temp_video_path)}")
        else:
             # Clip creation failed in the called function (e.g., create_speech_segment_clip_object)
             print(f"[Worker {os.getpid()}] Clip creation returned None for segment {segment_idx+1} ({segment_type}). Skipping write.")
             temp_video_path = None # Ensure path is None if clip is None

    except Exception as e:
        # Catch errors during the write_videofile call itself or other worker logic
        print(f"!!! Error in worker processing segment {segment_idx+1} ({segment_type}): {e}")
        temp_video_path = None # Ensure path is None on error
    finally:
        # Ensure the clip object is closed if it exists
        # This should handle cleanup of attached audio/visuals automatically
        if clip:
            try:
                 clip.close()
            except Exception as close_e:
                 # Log error but don't prevent returning the path if write succeeded before close failed
                 print(f"  Warn: Error closing clip in worker {os.getpid()} for segment {segment_idx+1}: {close_e}")

    # Return the path to the generated temp file (or None)
    return temp_video_path

# --- FFmpeg Padding Generation Helper Removed ---


# --- Main Function ---
def main(config_path, output_path, args):
    """
    Main execution flow. Generates segments in parallel using MoviePy workers,
    then concatenates them using an external FFmpeg command for memory efficiency.
    Assumes audio segments provided via config_json already contain necessary padding.
    """
    start_time = time.time()
    temp_segment_paths_created = [] # Keep track of ALL temp files created (segments + padding)
    temp_padding_clips_to_close = [] # Keep track of padding clips created in main process

    # --- Global Variable Updates ---
    if args:
        global CHARACTER_SCALE, FADE_DURATION
        CHARACTER_SCALE = args.character_scale
        FADE_DURATION = args.video_fade
        print(f"Settings: Character Scale={CHARACTER_SCALE}, Video Fade={FADE_DURATION}")
        print(f"Intermediate Encoding: Preset={args.intermediate_preset}, CRF={args.intermediate_crf}, FPS={args.fps}") # Log intermediate settings
        print(f"Final Audio Encoding: Codec=aac, Bitrate={args.final_audio_bitrate}") # Log final audio bitrate
    else: print("Warning: Args object not provided, using default constants.")

    # --- Directories & Config ---
    # Determine base directory for temporary files
    if args and hasattr(args, 'temp_output_dir') and args.temp_output_dir:
        base_temp_dir = args.temp_output_dir
        print(f"Using custom base temporary directory: {base_temp_dir}")
    else:
        base_temp_dir = os.path.dirname(output_path)
        print(f"Using default base temporary directory: {base_temp_dir}")

    # Use unique subdirs for work/temp based on output filename to avoid conflicts
    output_filename_base = os.path.splitext(os.path.basename(output_path))[0]
    work_dir = os.path.join(base_temp_dir, f'{output_filename_base}_work_v4')
    temp_segments_dir = os.path.join(base_temp_dir, f'{output_filename_base}_temp_v4')
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(temp_segments_dir, exist_ok=True)
    print(f"Using work directory (audio copies): {work_dir}")
    print(f"Using temp directory (video segments): {temp_segments_dir}")

    if not os.path.exists(config_path):
        print(f"Error: Configuration file not found at {config_path}")
        return
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config_list = json.load(f)
        print(f"Configuration loaded from {config_path}")
    except Exception as e:
        print(f"Error loading configuration from {config_path}: {e}")
        return

    # --- Process Audio & Prepare Tasks (Sequential) ---
    print("\nProcessing audio files & preparing tasks...")
    tasks_for_workers = []
    for i, segment_info_original in enumerate(config_list):
        segment_type = segment_info_original.get('type', 'unknown')
        audio_path = segment_info_original.get('audio_path')
        copied_audio_path = audio_path

        if audio_path and '/tmp/' in audio_path:
            filename = os.path.basename(audio_path)
            new_path = os.path.join(work_dir, filename)
            copied_audio_path = new_path
            if not os.path.exists(new_path):
                 if os.path.exists(audio_path):
                    try: shutil.copy2(audio_path, new_path)
                    except Exception as copy_e:
                         print(f"  Error copying temp audio {audio_path} to {new_path}: {copy_e}")
                         copied_audio_path = None
                 else:
                    print(f"  Warning: Temp audio file not found: {audio_path} for segment {i+1} ({segment_type})")
                    copied_audio_path = None

        if segment_type == 'silence': continue
        if segment_type not in ['intro', 'speech', 'outro']:
             print(f"Skipping unknown segment type {segment_type} at index {i}")
             continue
        if segment_type == 'speech' and not copied_audio_path:
             print(f"Skipping segment {i+1} ({segment_type}) due to missing/invalid audio path.")
             continue

        task_data = {
            'type': segment_type, 'index': i,
            'speaker': segment_info_original.get('voice'),
            'audio_path': copied_audio_path,
            'bg_image': segment_info_original.get('bg_image'),
            'host_image': segment_info_original.get('host_image'),
            'guest_image': segment_info_original.get('guest_image')
        }
        tasks_for_workers.append(task_data)

    # --- Padding Calculation Removed ---
    # Padding is now assumed to be included in the audio files generated by orpheus_ttsv2.py

    if not tasks_for_workers:
        print("Error: No valid segments found to process after filtering.")
        return

    # --- Video Properties ---
    default_screen_size = (1280, 720)
    if args and args.resolution:
         try:
            width, height = map(int, args.resolution.split('x'))
            default_screen_size = (width, height)
            print(f"Using default resolution from args: {default_screen_size}")
         except Exception as res_e: print(f"Warning: Invalid resolution format '{args.resolution}', using 1280x720. Error: {res_e}")

    screen_size = default_screen_size
    first_bg = next((task['bg_image'] for task in tasks_for_workers if task.get('bg_image') and os.path.exists(task.get('bg_image'))), None)

    if first_bg:
        try:
            with Image.open(first_bg) as img: screen_size = img.size
            print(f"Determined screen size from first background '{os.path.basename(first_bg)}': {screen_size}")
        except Exception as e: print(f"Warning: Could not read size from {first_bg}, using default {screen_size}. Error: {e}")
    else: print(f"Warning: No valid background found, using default {screen_size}.")

    # --- Create Segment Clips in Parallel ---
    num_workers = args.workers if args and args.workers is not None and args.workers > 0 else multiprocessing.cpu_count()
    print(f"\nCreating {len(tasks_for_workers)} main segment clips using up to {num_workers} worker processes...")
    print(f"(Writing temporary segment files to: {temp_segments_dir})")

    worker_func = partial(process_segment_worker, screen_size=screen_size, args=args, temp_dir=temp_segments_dir, work_dir=work_dir)

    returned_temp_segment_paths = []
    pool_start_time = time.time()
    try:
        # Set start method explicitly before creating the pool
        start_method = 'fork' if os.name == 'posix' else 'spawn'
        try:
            current_method = multiprocessing.get_start_method(allow_none=True)
            if current_method is None or current_method != start_method:
                 multiprocessing.set_start_method(start_method, force=True)
            print(f"Attempting to use multiprocessing start method: '{multiprocessing.get_start_method()}' for pool")
        except Exception as start_method_e:
             print(f"Warning: Could not set multiprocessing start method to '{start_method}'. Using default. Error: {start_method_e}")

        with multiprocessing.Pool(processes=num_workers) as pool:
            returned_temp_segment_paths = pool.map(worker_func, tasks_for_workers)
    except Exception as pool_e:
         print(f"\n!!! Error during multiprocessing pool execution: {pool_e}")
    finally:
         # Add paths created by workers to the main cleanup list
         temp_segment_paths_created.extend(p for p in returned_temp_segment_paths if p is not None)

    pool_end_time = time.time()
    print(f"\nMultiprocessing pool finished in {pool_end_time - pool_start_time:.2f} seconds.")

    # Filter out None paths which indicate failed segments
    valid_temp_segment_paths = [p for p in returned_temp_segment_paths if p is not None]
    if len(valid_temp_segment_paths) != len(tasks_for_workers):
         print(f"Warning: {len(tasks_for_workers) - len(valid_temp_segment_paths)} segment(s) failed during processing.")

    # --- Prepare Final List for FFmpeg Concat (Main Segments Only) ---
    final_concat_paths = []
    list_file_path = os.path.join(temp_segments_dir, "ffmpeg_concat_list.txt")

    try:
        print(f"\nPreparing FFmpeg concat list (using main segments only)...")

        # Map original task index to the path of the successfully created segment file
        successful_segment_map = {task_data['index']: path
                                  for task_data, path in zip(tasks_for_workers, returned_temp_segment_paths)
                                  if path is not None}

        # Iterate through the original task list to maintain order
        for i, task_data in enumerate(tasks_for_workers):
            original_index = task_data['index']
            temp_segment_path = successful_segment_map.get(original_index)

            if temp_segment_path: # Check if this segment was successfully created
                final_concat_paths.append(os.path.abspath(temp_segment_path)) # Add main segment path
            else:
                 print(f"  Skipping segment {original_index+1} ({task_data['type']}) in final concatenation list as it failed processing.")

        # --- Padding Generation Removed ---
        # Padding is now part of the audio files themselves.

        if not final_concat_paths:
            print("Error: No valid segment files available for concatenation (all segments might have failed).")
            return # Cleanup happens in finally

        # Create the FFmpeg concat list file
        print(f"\nCreating FFmpeg concatenation list: {list_file_path}")
        with open(list_file_path, 'w', encoding='utf-8') as f:
            for path in final_concat_paths:
                 # Use repr() to handle potential special characters safely for FFmpeg list file
                 f.write(f"file {repr(path)}\n")
        print(f"Successfully created concatenation list with {len(final_concat_paths)} entries.")

        # --- Concatenate using FFmpeg ---
        print(f"\nConcatenating segments and re-encoding audio using FFmpeg into: {output_path}")
        # Copy video stream, re-encode audio stream to AAC
        ffmpeg_command = [
            'ffmpeg',
            '-f', 'concat',
            '-safe', '0', # Necessary for using absolute/relative paths in the list file
            '-i', list_file_path,
            '-c:v', 'copy',       # Copy video stream
            '-c:a', 'aac',        # Re-encode audio to AAC
            '-b:a', args.final_audio_bitrate, # Set audio bitrate from args
            '-y',                 # Overwrite output
            output_path
        ]

        print(f"Running FFmpeg command: {' '.join(shlex.quote(arg) for arg in ffmpeg_command)}")
        ffmpeg_start_time = time.time()
        try:
            result = subprocess.run(ffmpeg_command, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
            ffmpeg_end_time = time.time()
            # Print ffmpeg output only if verbose or on error? For now, print always.
            print("--- FFmpeg stdout ---")
            print(result.stdout if result.stdout else "<No stdout>")
            print("--- FFmpeg stderr ---")
            print(result.stderr if result.stderr else "<No stderr>")
            print(f"\nFFmpeg concatenation successful in {ffmpeg_end_time - ffmpeg_start_time:.2f} seconds.")
            print(f"✅ Video successfully generated: {output_path}")

        except FileNotFoundError:
             print("\nERROR: 'ffmpeg' command not found. Make sure FFmpeg is installed and in your system PATH.")
             # No need to return, finally block will handle cleanup
        except subprocess.CalledProcessError as ffmpeg_e:
            print(f"\nERROR: FFmpeg command failed with return code {ffmpeg_e.returncode}")
            print("--- FFmpeg stdout ---")
            print(ffmpeg_e.stdout if ffmpeg_e.stdout else "<No stdout>")
            print("--- FFmpeg stderr ---")
            print(ffmpeg_e.stderr if ffmpeg_e.stderr else "<No stderr>")
            # No need to return, finally block will handle cleanup
        except Exception as e:
            print(f"\nAn unexpected error occurred during FFmpeg execution: {e}")
            # No need to return, finally block will handle cleanup

    except Exception as main_err:
        print(f"\nError during main processing stage (padding/list gen/ffmpeg): {main_err}")
        # Fall through to finally for cleanup

    finally:
        # --- Cleanup ---
        print("\nCleaning up...")
        # --- Padding Clip Closing Removed ---

        # Remove concat list file
        if os.path.exists(list_file_path) and not (args and args.keep_temp_files):
            try:
                os.remove(list_file_path)
                print(f"  Removed FFmpeg list file: {list_file_path}")
            except Exception as rem_e:
                print(f"  Warn: Could not remove list file {list_file_path}: {rem_e}")

        # Remove temporary segment files
        if args and args.keep_temp_files:
             print(f"Keeping temporary segment files in {temp_segments_dir} as requested.")
        else:
             # temp_segment_paths_created now only contains main segment paths (and failed padding paths if any error occurred)
             print(f"Removing {len(temp_segment_paths_created)} temporary segment files from {temp_segments_dir}...")
             deleted_count = 0
             for temp_path in temp_segment_paths_created: # Iterate over paths created by workers
                  if temp_path and os.path.exists(temp_path):
                      try:
                          os.remove(temp_path)
                          deleted_count += 1
                      except Exception as rem_e:
                          print(f"  Warn: Could not remove temporary file {temp_path}: {rem_e}")
             print(f"  Removed {deleted_count} files.")

        # Optionally remove work dir if empty? For now, keep it.
        # Optionally remove temp dir if empty? For now, keep it.

        print("Cleanup finished.")
        end_time = time.time()
        print(f"\nTotal execution time: {end_time - start_time:.2f} seconds.")


if __name__ == "__main__":
    # --- Set Multiprocessing Start Method ---
    # Moved setting start_method inside main() just before creating the pool
    # to potentially avoid issues if the script is imported elsewhere.
    # Initial print remains here for info.
    start_method = 'fork' if os.name == 'posix' else 'spawn'
    print(f"Default multiprocessing start method for OS: '{start_method}'")


    # --- Argument Parsing ---
    parser = argparse.ArgumentParser(
        description="Generate podcast video using parallel workers and FFmpeg concatenation (v4). Uses MoviePy for padding.", # Updated description
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    # Required
    parser.add_argument("config_json", help="Path to the JSON configuration file")
    parser.add_argument("output_video", help="Path to save the final output video file")
    # Intermediate Encoding (Controls quality of intermediate segment files)
    encode_group = parser.add_argument_group('Intermediate Segment Encoding Options')
    encode_group.add_argument("--fps", type=int, default=24, help="Frames per second for intermediate segments")
    encode_group.add_argument("--intermediate-preset", default='medium',
                            help="Encoding preset for intermediate libx264 segments (e.g., ultrafast, medium, slow, veryslow). Slower presets = better quality/compression.")
    encode_group.add_argument("--intermediate-crf", type=int, default=23,
                            help="CRF value for intermediate libx264 segments (0-51). Lower is higher quality. 18-24 is typical range. 0 is lossless.")
    # Final Audio Encoding
    audio_group = parser.add_argument_group('Final Audio Encoding Options')
    audio_group.add_argument("--final-audio-bitrate", default='192k',
                           help="Bitrate for final AAC audio encoding (e.g., 128k, 192k, 256k).")
    # Visual
    visual_group = parser.add_argument_group('Visual Options')
    visual_group.add_argument("--character-scale", type=float, default=1.0, help="Scale factor for characters")
    visual_group.add_argument("--resolution", default="1280x720", help="Default resolution if no background (WxH)")
    visual_group.add_argument("--video-fade", type=float, default=1.0, help="Video fade duration (for intro/outro segments)")
    # Intro/Outro Audio
    io_audio_group = parser.add_argument_group('Intro/Outro Audio Options')
    io_audio_group.add_argument("--audio-fadein", type=float, default=5.0, help="Audio fade-in duration for outro")
    io_audio_group.add_argument("--audio-fadeout", type=float, default=5.0, help="Audio fade-out duration for intro")
    # Performance
    perf_group = parser.add_argument_group('Performance and Debugging Options')
    perf_group.add_argument("--workers", type=int, default=None, help="Number of worker processes for parallel clip generation. Defaults to CPU count.")
    perf_group.add_argument("--keep-temp-files", action='store_true', help="Keep temporary audio/video segment/padding files and list file after completion.")
    perf_group.add_argument("--temp-output-dir", type=str, default=None, help="Optional: Base directory for temporary work and segment files. Defaults to output_video's directory.")

    args = parser.parse_args()

    # --- Determine Worker Count ---
    if args.workers is None:
        try: args.workers = multiprocessing.cpu_count()
        except NotImplementedError: args.workers = 1
        print(f"Number of workers not specified, defaulting to CPU count: {args.workers}")
    elif args.workers <= 0:
         print(f"Warning: Invalid number of workers ({args.workers}), defaulting to 1.")
         args.workers = 1

    # --- Run Main ---
    main(args.config_json, args.output_video, args)