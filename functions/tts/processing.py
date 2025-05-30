import os
import subprocess # Added for subprocess.run
import shlex
import tempfile
import shutil
import numpy as np
import soundfile as sf

try:
    from pydub import AudioSegment
    pydub_available = True
except ImportError:
    print("Warning: 'pydub' library not found. Audio manipulation (gain, trim, padding) disabled.")
    pydub_available = False

def apply_audio_enhancements(audio_path, config, temp_dir):
    """
    Applies FFmpeg enhancements (noise reduction, compression, normalization, de-essing)
    and pydub processing (gain, trim, padding) to an audio file.

    Args:
        audio_path (str): Path to the input audio file.
        config (dict): Dictionary containing processing parameters (e.g., nr_level, gain_factor, etc.).
        temp_dir (str): Path to a temporary directory for intermediate files.

    Returns:
        tuple: (path_to_processed_file, samplerate) or (None, None) on failure.
    """
    processed_audio_path = audio_path
    samplerate = None

    if not os.path.exists(audio_path):
        print(f"Error: Input audio file not found for processing: {audio_path}")
        return None, None

    # Get samplerate from the initial audio file
    try:
        info = sf.info(audio_path)
        samplerate = info.samplerate
    except Exception as e:
        print(f"Error getting samplerate from {audio_path}: {e}")
        return None, None

    # --- FFmpeg Enhancement (Conditional) ---
    final_apply_ffmpeg = config.get('apply_ffmpeg_enhancement', True)
    final_apply_deesser = config.get('apply_deesser', True) # Default ON
    final_deesser_freq = config.get('deesser_freq', 3000)
    final_nr_level = config.get('nr_level', 0)
    final_compress_thresh = config.get('compress_thresh', 1.0)
    final_compress_ratio = config.get('compress_ratio', 1)
    final_norm_frame_len = config.get('norm_frame_len', 10)
    final_norm_gauss_size = config.get('norm_gauss_size', 3)

    ffmpeg_temp_path = None

    if final_apply_ffmpeg:
        # Ensure final norm_gauss_size is odd
        if final_norm_gauss_size % 2 == 0:
            final_norm_gauss_size -= 1
            print(f"  Adjusting Norm Gauss size from {final_norm_gauss_size + 1} to {final_norm_gauss_size} (must be odd).")

        ffmpeg_temp_fd, ffmpeg_temp_path = tempfile.mkstemp(suffix="_ffmpeg.wav", prefix="segment_", dir=temp_dir)
        os.close(ffmpeg_temp_fd)

        try:
            filter_chain = []

            if final_apply_deesser:
                filter_chain.append(f"firequalizer=gain='if(gte(f,{final_deesser_freq}),-5,0)'")

            if final_nr_level > 0:
                filter_chain.append(f"afftdn=nr={final_nr_level}")

            comp_thresh_str = f"{final_compress_thresh:.3f}"
            filter_chain.append(f"acompressor=threshold={comp_thresh_str}:ratio={final_compress_ratio}:attack=10:release=100")

            filter_chain.append(f"dynaudnorm=f={final_norm_frame_len}:g={final_norm_gauss_size}")

            audio_filter = ','.join(filter_chain)

            ffmpeg_command = [
                'ffmpeg',
                '-i', audio_path,
                '-af', audio_filter,
                '-y',
                ffmpeg_temp_path
            ]
            print(f"  Attempting FFmpeg enhancement: {' '.join(shlex.quote(arg) for arg in ffmpeg_command)}")
            result = subprocess.run(ffmpeg_command, capture_output=True, text=True, check=False)

            if result.returncode == 0 and os.path.exists(ffmpeg_temp_path) and os.path.getsize(ffmpeg_temp_path) > 44:
                processed_audio_path = ffmpeg_temp_path
                print(f"  -> SUCCESS: FFmpeg enhancement saved to: {os.path.basename(ffmpeg_temp_path)}")
            else:
                print(f"  !! Warning: FFmpeg processing failed or produced empty file. Using original audio.")
                print(f"     Return Code: {result.returncode}")
                print(f"     Stderr: {result.stderr.strip()}")
                if os.path.exists(ffmpeg_temp_path):
                    try: os.remove(ffmpeg_temp_path)
                    except OSError: pass
                ffmpeg_temp_path = None
        except FileNotFoundError:
            print(f"  !! Error: 'ffmpeg' command not found. Skipping enhancement.")
            if ffmpeg_temp_path and os.path.exists(ffmpeg_temp_path):
                try: os.remove(ffmpeg_temp_path)
                except OSError: pass
            ffmpeg_temp_path = None
        except Exception as ffmpeg_e:
            print(f"  !! Warning: Error running FFmpeg processing: {ffmpeg_e}. Skipping enhancement.")
            if ffmpeg_temp_path and os.path.exists(ffmpeg_temp_path):
                try: os.remove(ffmpeg_temp_path)
                except OSError: pass
            ffmpeg_temp_path = None
    else:
        print("  -> Skipping FFmpeg enhancement as requested.")

    # --- Pydub Processing (Gain, Trim, Pad) ---
    final_gain_factor = config.get('gain_factor', 1.0)
    final_trim_end_ms = config.get('trim_end_ms', 0)
    pad_end_ms = config.get('pad_end_ms', 0)

    if pydub_available:
        try:
            print(f"  Processing with pydub (Gain, Trim, Pad) on: {os.path.basename(processed_audio_path)}...")
            segment = AudioSegment.from_wav(processed_audio_path)
            samplerate = segment.frame_rate

            if final_gain_factor != 1.0 and final_gain_factor > 0:
                print(f"    -> Applying gain: {final_gain_factor:.2f}x")
                gain_db = 20 * np.log10(final_gain_factor)
                segment = segment + gain_db

            if final_trim_end_ms > 0 and len(segment) > final_trim_end_ms:
                print(f"    -> Trimming {final_trim_end_ms}ms from end.")
                segment = segment[:-final_trim_end_ms]
            elif final_trim_end_ms > 0:
                 print(f"    -> Warning: Segment length ({len(segment)}ms) is less than trim duration ({final_trim_end_ms}ms). Skipping trim.")

            if pad_end_ms > 0:
                print(f"    -> Padding {pad_end_ms}ms silence to end.")
                padding = AudioSegment.silent(duration=pad_end_ms, frame_rate=samplerate)
                segment = segment + padding
            else:
                 print(f"    -> No end padding requested (pad_end_ms={pad_end_ms}).")

            # Create a new temp file for the final pydub output
            pydub_temp_fd, pydub_temp_path = tempfile.mkstemp(suffix="_pydub.wav", prefix="segment_", dir=temp_dir)
            os.close(pydub_temp_fd)

            print(f"  -> Exporting final processed audio to {os.path.basename(pydub_temp_path)}")
            segment.export(pydub_temp_path, format="wav")
            duration = len(segment) / 1000.0
            print(f"  -> Final segment saved ({duration:.2f}s, SR: {samplerate} Hz)")
            
            # Cleanup the intermediate FFmpeg file if it was created
            if ffmpeg_temp_path and os.path.exists(ffmpeg_temp_path):
                try: os.remove(ffmpeg_temp_path)
                except OSError as e: print(f"  Warning: Could not remove ffmpeg temp file {ffmpeg_temp_path}: {e}")

            return pydub_temp_path, samplerate

        except Exception as pydub_e:
            print(f"!! Error during pydub processing: {pydub_e}")
            print(f"!! Falling back to using the pre-pydub audio: {os.path.basename(processed_audio_path)}")
            # If pydub fails, try to copy the ffmpeg/initial file to the final path
            try:
                final_fd, final_path_on_error = tempfile.mkstemp(suffix="_final_fallback.wav", prefix="segment_", dir=temp_dir)
                os.close(final_fd)
                shutil.copy2(processed_audio_path, final_path_on_error)
                # Need to get samplerate if we didn't get it from pydub
                if samplerate is None:
                    with sf.SoundFile(final_path_on_error) as audio_info:
                        samplerate = audio_info.samplerate
                
                # Cleanup the intermediate FFmpeg file if it was created
                if ffmpeg_temp_path and os.path.exists(ffmpeg_temp_path):
                    try: os.remove(ffmpeg_temp_path)
                    except OSError as e: print(f"  Warning: Could not remove ffmpeg temp file {ffmpeg_temp_path}: {e}")

                return final_path_on_error, samplerate
            except Exception as copy_e:
                 print(f"!! Error copying fallback audio: {copy_e}")
                 return None, None
    else:
        print("!! Pydub not available. Skipping gain, trim, and padding.")
        # If pydub is not available, the processed_audio_path (from FFmpeg or initial) is the final one.
        # We should copy it to a new temp file to ensure it's not the original input file.
        try:
            final_fd, final_path_no_pydub = tempfile.mkstemp(suffix="_final_nopydub.wav", prefix="segment_", dir=temp_dir)
            os.close(final_fd)
            shutil.copy2(processed_audio_path, final_path_no_pydub)
            
            # Cleanup the intermediate FFmpeg file if it was created
            if ffmpeg_temp_path and os.path.exists(ffmpeg_temp_path):
                try: os.remove(ffmpeg_temp_path)
                except OSError as e: print(f"  Warning: Could not remove ffmpeg temp file {ffmpeg_temp_path}: {e}")

            return final_path_no_pydub, samplerate
        except Exception as copy_e:
             print(f"!! Error copying non-pydub audio: {copy_e}")
             return None, None