import requests
import soundfile as sf
import io
import numpy as np
import os
import tempfile
import shutil
import shlex
import subprocess # Added for subprocess.run
import time # Added for retry delays
from functions.tts.utils import load_voice_config

# Override print function to force immediate flushing for real-time output
original_print = print
def print(*args, **kwargs):
    kwargs.setdefault('flush', True)
    return original_print(*args, **kwargs)

def make_tts_request_with_retry(api_url, payload, headers, max_retries=3, timeout=180):
    """
    Makes a TTS API request with retry logic and exponential backoff.
    
    Args:
        api_url (str): The API endpoint URL
        payload (dict): Request payload
        headers (dict): Request headers
        max_retries (int): Maximum number of retry attempts (default: 3)
        timeout (int): Request timeout in seconds (default: 180)
    
    Returns:
        requests.Response: Successful response object
        
    Raises:
        requests.exceptions.RequestException: If all retries fail
    """
    for attempt in range(max_retries + 1):  # +1 for initial attempt
        try:
            if attempt > 0:
                # Exponential backoff: wait 2^attempt seconds (2, 4, 8 seconds)
                wait_time = 2 ** attempt
                print(f"   Retry attempt {attempt}/{max_retries} in {wait_time} seconds...")
                time.sleep(wait_time)
            
            print(f"-> Making TTS request to {api_url} (attempt {attempt + 1}/{max_retries + 1})")
            response = requests.post(api_url, json=payload, headers=headers, timeout=timeout)
            response.raise_for_status()
            
            if response.content and len(response.content) > 44:  # Valid audio response
                print(f"   ✅ SUCCESS on attempt {attempt + 1}")
                return response
            else:
                raise requests.exceptions.RequestException(f"Empty or invalid audio response (Size: {len(response.content)} bytes)")
                
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            print(f"   ❌ Network error on attempt {attempt + 1}: {e}")
            if attempt == max_retries:
                raise e
            continue
            
        except requests.exceptions.HTTPError as e:
            print(f"   ❌ HTTP error on attempt {attempt + 1}: {e}")
            if response and response.text:
                print(f"   Response content: {response.text}")
            if attempt == max_retries:
                raise e
            continue
            
        except requests.exceptions.RequestException as e:
            print(f"   ❌ Request error on attempt {attempt + 1}: {e}")
            if attempt == max_retries:
                raise e
            continue
            
    # This should never be reached, but just in case
    raise requests.exceptions.RequestException(f"All {max_retries + 1} attempts failed")

def generate_audio_segment(input_text, voice, speed, api_host, api_port, temp_dir,
                           # Parameters that can be overridden by function call
                           apply_deesser=None, # Boolean toggle (True/False/None)
                           deesser_freq=None,  # Explicit frequency or None
                           gain_factor=None,   # Explicit gain or None
                           trim_end_ms=None,   # Explicit trim or None
                           pad_end_ms=0,       # Explicit padding (defaults to 0)
                           apply_ffmpeg_enhancement=None, # Boolean toggle (True/False/None)
                           nr_level=None,         # Explicit NR level or None
                           compress_thresh=None,  # Explicit threshold or None
                           compress_ratio=None,   # Explicit ratio or None
                           norm_frame_len=None,   # Explicit frame len or None
                           norm_gauss_size=None,  # Explicit gauss size or None
                           max_retries=3,         # Maximum retry attempts
                           timeout=180):          # Request timeout in seconds
    """
    Generates a single audio segment, optionally applies FFmpeg enhancement (de-ess, NR, norm),
    applies gain, trimming, and padding using pydub, and saves it to a temporary file.
    Default enhancement parameters are set based on the selected voice.

    Args:
        input_text (str): Text to synthesize.
        voice (str): Voice model name.
        speed (float): Speech speed.
        api_host (str): API hostname/IP.
        api_port (int): API port.
        temp_dir (str): Path to temporary directory.
        gain_factor (float, optional): Gain multiplier. Defaults to 1.0.
        trim_end_ms (int, optional): Milliseconds to trim from the end. Defaults to 120.
        pad_end_ms (int, optional): Milliseconds of silence to pad at the end. Defaults to 0.
        apply_ffmpeg_enhancement (bool, optional): Whether to apply FFmpeg processing. Defaults to True.


    Returns:
        tuple: (path_to_final_file, samplerate) or (None, None) on failure.
    """
    # Try OpenAI-compatible endpoint first, fallback to legacy if needed
    api_url = f"http://{api_host}:{api_port}/v1/audio/speech"
    
    payload = {
        "model": "orpheus",
        "input": input_text,
        "voice": voice,
        "response_format": "wav",
        "speed": speed
    }
    
    headers = {
        "Content-Type": "application/json"
    }

    print(f"\nGenerating segment for voice '{voice}' (Speed: {speed}): \"{input_text[:50]}...\"")

    # --- Load Voice Configuration from YAML ---
    voice_config = load_voice_config(voice)

    # --- Determine Final Parameter Values ---
    # Use passed value if not None, otherwise use value from loaded config
    final_gain_factor = gain_factor if gain_factor is not None else voice_config.get('gain_factor', 1.0)
    final_trim_end_ms = trim_end_ms if trim_end_ms is not None else voice_config.get('trim_end_ms', 0)
    final_nr_level = nr_level if nr_level is not None else voice_config.get('nr_level', 0)
    final_compress_thresh = compress_thresh if compress_thresh is not None else voice_config.get('compress_thresh', 1.0)
    final_compress_ratio = compress_ratio if compress_ratio is not None else voice_config.get('compress_ratio', 1)
    final_norm_frame_len = norm_frame_len if norm_frame_len is not None else voice_config.get('norm_frame_len', 10)
    final_norm_gauss_size = norm_gauss_size if norm_gauss_size is not None else voice_config.get('norm_gauss_size', 3)
    final_deesser_freq = deesser_freq if deesser_freq is not None else voice_config.get('deesser_freq', 3000)

    # Determine boolean toggles (NOT from YAML, use passed value or default logic)
    final_apply_ffmpeg = apply_ffmpeg_enhancement if apply_ffmpeg_enhancement is not None else True # Default ON
    final_apply_deesser = apply_deesser if apply_deesser is not None else (True if voice != 'leo' else False) # Default ON except Leo

    # Ensure final norm_gauss_size is odd if FFmpeg is applied
    if final_apply_ffmpeg and final_norm_gauss_size % 2 == 0:
        print(f"  Adjusting Norm Gauss size from {final_norm_gauss_size} to {final_norm_gauss_size - 1} (must be odd).")
        final_norm_gauss_size -= 1

    samplerate = None # Initialize samplerate
    final_temp_path = None # Path for the final output of this function (created by mkstemp)
    initial_temp_path = None # Path for the raw API output
    ffmpeg_temp_path = None # Path for the FFmpeg processed output
    processed_audio_path = None # Path to the audio file before pydub processing

    try:
        response = None
        try:
            # Try OpenAI-compatible endpoint first with retry logic
            print(f"Attempting OpenAI-compatible endpoint at {api_url}")
            response = make_tts_request_with_retry(api_url, payload, headers, max_retries=max_retries, timeout=timeout)
        except requests.exceptions.RequestException as api_err:
            print(f"!! OpenAI-compatible endpoint failed after all retries: {api_err}")
            
            print("!! Attempting legacy endpoint fallback with retries...")
            
            # Fallback to legacy endpoint with retry logic
            legacy_url = f"http://{api_host}:{api_port}/speak"
            legacy_payload = {
                "text": input_text,
                "voice": voice
            }
            try:
                print(f"Attempting legacy endpoint at {legacy_url}")
                response = make_tts_request_with_retry(legacy_url, legacy_payload, headers, max_retries=max_retries, timeout=timeout)
            except requests.exceptions.RequestException as legacy_err:
                print(f"!! Legacy endpoint also failed after all retries: {legacy_err}")
                print(f"!! CRITICAL: Unable to generate audio segment after all retry attempts.")
                print(f"!! Please check TTS server status and try again.")
                return None, None

        if response.content and len(response.content) > 44: # Check for more than just header
            # Use mkstemp for the *final* unique file name, we'll overwrite it later
            # Ensure temp_dir is used for mkstemp
            temp_fd, final_temp_path = tempfile.mkstemp(suffix=".wav", prefix="segment_", dir=temp_dir)
            os.close(temp_fd)

            # Create another temp file for the initial raw API output
            # Ensure temp_dir is used for mkstemp
            initial_fd, initial_temp_path = tempfile.mkstemp(suffix="_initial.wav", prefix="segment_", dir=temp_dir)
            os.close(initial_fd)

            try:
                # --- 1. Save Initial API Response ---
                with open(initial_temp_path, 'wb') as f_initial:
                    f_initial.write(response.content)
                print(f"-> Initial API response saved to {os.path.basename(initial_temp_path)}")
                processed_audio_path = initial_temp_path # Default to initial if FFmpeg fails

                # --- 2. FFmpeg Enhancement (Conditional) ---
                if final_apply_ffmpeg: # Use the final determined boolean
                    # Ensure temp_dir is used for mkstemp
                    ffmpeg_temp_fd, ffmpeg_temp_path = tempfile.mkstemp(suffix="_ffmpeg.wav", prefix="segment_", dir=temp_dir)
                    os.close(ffmpeg_temp_fd)
                else:
                    ffmpeg_temp_path = None # Ensure path is None if skipping
                    print("  -> Skipping FFmpeg enhancement as requested.")

                # Only run FFmpeg if requested and path was created
                if final_apply_ffmpeg and ffmpeg_temp_path: # Use the final determined boolean
                    try:
                        # Build the ffmpeg audio filter string dynamically
                        af_parts = []

                        # Build filter chain in correct order using final parameter values
                        filter_chain = []

                        # 1. De-esser (if enabled)
                        if final_apply_deesser: # Use final boolean
                            filter_chain.append(f"firequalizer=gain='if(gte(f,{final_deesser_freq}),-5,0)'") # Use final freq

                        # 2. Noise Reduction
                        if final_nr_level > 0: # Only add NR if level is > 0
                            filter_chain.append(f"afftdn=nr={final_nr_level}") # Use final level

                        # 3. Compression
                        comp_thresh_str = f"{final_compress_thresh:.3f}" # Use final thresh
                        filter_chain.append(f"acompressor=threshold={comp_thresh_str}:ratio={final_compress_ratio}:attack=10:release=100") # Use final ratio

                        # 4. Normalization (gauss size already ensured odd)
                        filter_chain.append(f"dynaudnorm=f={final_norm_frame_len}:g={final_norm_gauss_size}") # Use final frame/gauss

                        # Join all filters with commas
                        audio_filter = ','.join(filter_chain)

                        ffmpeg_command = [
                            'ffmpeg',
                            '-i', initial_temp_path,
                            '-af', audio_filter,
                            '-y', # Overwrite output
                            ffmpeg_temp_path
                        ]
                        print(f"  Attempting FFmpeg enhancement: {' '.join(shlex.quote(arg) for arg in ffmpeg_command)}")
                        result = subprocess.run(ffmpeg_command, capture_output=True, text=True, check=False)

                        if result.returncode == 0 and os.path.exists(ffmpeg_temp_path) and os.path.getsize(ffmpeg_temp_path) > 44:
                            processed_audio_path = ffmpeg_temp_path
                            print(f"  -> SUCCESS: FFmpeg enhancement saved to: {os.path.basename(ffmpeg_temp_path)}")
                        else:
                            print(f"  !! Warning: FFmpeg processing failed or produced empty file. Using initial audio.")
                            print(f"     Return Code: {result.returncode}")
                            print(f"     Stderr: {result.stderr.strip()}")
                            # processed_audio_path remains initial_temp_path
                            # Clean up empty/failed ffmpeg file
                            if os.path.exists(ffmpeg_temp_path):
                                try: os.remove(ffmpeg_temp_path)
                                except OSError: pass
                            ffmpeg_temp_path = None # Mark as unused
                    except FileNotFoundError:
                        print(f"  !! Error: 'ffmpeg' command not found. Skipping enhancement.")
                        processed_audio_path = initial_temp_path # Fallback
                        ffmpeg_temp_path = None # Mark as unused
                    except Exception as ffmpeg_e:
                        print(f"  !! Warning: Error running FFmpeg processing: {ffmpeg_e}. Skipping enhancement.")
                        processed_audio_path = initial_temp_path # Fallback
                        if ffmpeg_temp_path and os.path.exists(ffmpeg_temp_path): # Clean up if created
                            try: os.remove(ffmpeg_temp_path)
                            except OSError: pass
                        ffmpeg_temp_path = None # Mark as unused
                else:
                    # If FFmpeg was skipped, the initial path is the one to process
                    processed_audio_path = initial_temp_path

                # --- 3. Pydub Processing (Gain, Trim, Pad) ---
                try:
                    from pydub import AudioSegment # For audio manipulation (pip install pydub)
                    pydub_available = True
                except ImportError:
                    pydub_available = False

                if pydub_available:
                    try:
                        print(f"  Processing with pydub (Gain, Trim, Pad) on: {os.path.basename(processed_audio_path)}...")
                        segment = AudioSegment.from_wav(processed_audio_path)
                        samplerate = segment.frame_rate # Get samplerate from loaded segment

                        # Apply Gain
                        if final_gain_factor != 1.0 and final_gain_factor > 0: # Use final value
                            print(f"    -> Applying gain: {final_gain_factor:.2f}x")
                            # pydub uses dB for gain, convert factor to dB: dB = 20 * log10(factor)
                            gain_db = 20 * np.log10(final_gain_factor) # Use final value
                            segment = segment + gain_db # Add dB gain
                            # Pydub handles clipping internally during export usually

                        # Apply Trimming (from end)
                        if final_trim_end_ms > 0 and len(segment) > final_trim_end_ms: # Use final value
                            print(f"    -> Trimming {final_trim_end_ms}ms from end.") # Use final value
                            segment = segment[:-final_trim_end_ms] # Use final value
                        elif final_trim_end_ms > 0: # Use final value
                             print(f"    -> Warning: Segment length ({len(segment)}ms) is less than trim duration ({final_trim_end_ms}ms). Skipping trim.") # Use final value


                        # Apply Silence Padding (to end)
                        if pad_end_ms > 0:
                            print(f"    -> Padding {pad_end_ms}ms silence to end.")
                            padding = AudioSegment.silent(duration=pad_end_ms, frame_rate=samplerate)
                            segment = segment + padding
                        else:
                             print(f"    -> No end padding requested (pad_end_ms={pad_end_ms}).")


                        # Export final processed audio to the final_temp_path (overwriting the initial empty file)
                        print(f"  -> Exporting final processed audio to {os.path.basename(final_temp_path)}")
                        segment.export(final_temp_path, format="wav")
                        duration = len(segment) / 1000.0 # Duration in seconds
                        print(f"  -> Final segment saved ({duration:.2f}s, SR: {samplerate} Hz)")
                        return final_temp_path, samplerate # Return the path to the final overwritten file

                    except Exception as pydub_e:
                        print(f"!! Error during pydub processing: {pydub_e}")
                        print(f"!! Falling back to using the pre-pydub audio: {os.path.basename(processed_audio_path)}")
                        # If pydub fails, try to copy the ffmpeg/initial file to the final path
                        try:
                            shutil.copy2(processed_audio_path, final_temp_path)
                            # Need to get samplerate if we didn't get it from pydub
                            if samplerate is None:
                                with sf.SoundFile(final_temp_path) as audio_info:
                                    samplerate = audio_info.samplerate
                            return final_temp_path, samplerate
                        except Exception as copy_e:
                             print(f"!! Error copying fallback audio: {copy_e}")
                             return None, None # Indicate failure
                else:
                    # Pydub not available, copy the ffmpeg/initial file to the final path
                    print("!! Pydub not available. Skipping gain, trim, and padding.")
                    try:
                        shutil.copy2(processed_audio_path, final_temp_path)
                        # Need to get samplerate
                        with sf.SoundFile(final_temp_path) as audio_info:
                            samplerate = audio_info.samplerate
                        return final_temp_path, samplerate
                    except Exception as copy_e:
                         print(f"!! Error copying non-pydub audio: {copy_e}")
                         return None, None # Indicate failure

            except Exception as e:
                print(f"!! Error processing/saving segment: {e}")
                return None, None # Indicate failure
            finally:
                # --- Cleanup Intermediate Files ---
                if initial_temp_path and os.path.exists(initial_temp_path):
                    try: os.remove(initial_temp_path)
                    except OSError as e: print(f"  Warning: Could not remove initial temp file {initial_temp_path}: {e}")
                if ffmpeg_temp_path and os.path.exists(ffmpeg_temp_path):
                    try: os.remove(ffmpeg_temp_path)
                    except OSError as e: print(f"  Warning: Could not remove ffmpeg temp file {ffmpeg_temp_path}: {e}")
                # Do NOT remove final_temp_path here, it's the intended return value

        else:
            print(f"!! Received empty or invalid audio data (Size: {len(response.content)} bytes). Skipping segment.")
            return None, None

    except requests.exceptions.RequestException as e:
        print(f"!! Error during API request: {e}")
        return None, None
    except Exception as e:
        print(f"!! An unexpected error occurred during generation: {e}")
        # Clean up final_temp_path if it was created but an error occurred before return
        if final_temp_path and os.path.exists(final_temp_path):
             try: os.remove(final_temp_path)
             except OSError as e: print(f"  Warning: Could not remove final temp file on error {final_temp_path}: {e}")
        return None, None