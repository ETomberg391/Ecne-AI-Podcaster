import os
import yaml
import numpy as np
import soundfile as sf
import tempfile
import shutil
from scipy.signal import resample # For resampling in concatenate_wavs

# Define VOICE_DIR relative to the project root, assuming functions/tts/utils.py is in functions/tts/
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..')) # Go up two levels from functions/tts/
VOICE_DIR = os.path.abspath(os.path.join(PROJECT_ROOT, "settings/voices"))
os.makedirs(VOICE_DIR, exist_ok=True) # Ensure VOICE_DIR exists

def load_voice_config(voice_name):
    """Loads voice configuration from YAML file, falling back to default."""
    base_path = os.path.join(VOICE_DIR, f"{voice_name}.yaml")
    default_path = os.path.join(VOICE_DIR, "default.yaml")
    config_path = base_path if os.path.exists(base_path) else default_path

    # Hardcoded fallback defaults in case even default.yaml is missing/invalid
    hardcoded_defaults = {
        'gain_factor': 1.0, 'trim_end_ms': 0, 'nr_level': 0,
        'compress_thresh': 1.0, 'compress_ratio': 1, 'norm_frame_len': 10,
        'norm_gauss_size': 3, 'deesser_freq': 3000
    }

    if not os.path.exists(config_path):
        print(f"!! Warning: Voice config not found for '{voice_name}' and default.yaml missing. Using hardcoded defaults.")
        return hardcoded_defaults

    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        if config is None: # Handle empty YAML file
            print(f"!! Warning: Voice config file '{os.path.basename(config_path)}' is empty. Using hardcoded defaults.")
            return hardcoded_defaults
        print(f"-> Loaded voice config from: {os.path.basename(config_path)}")
        # Merge with hardcoded defaults to ensure all keys exist
        final_config = hardcoded_defaults.copy()
        final_config.update(config)
        return final_config
    except yaml.YAMLError as e:
        print(f"!! Error parsing voice config file '{os.path.basename(config_path)}': {e}. Using hardcoded defaults.")
        return hardcoded_defaults
    except Exception as e:
        print(f"!! Error loading voice config file '{os.path.basename(config_path)}': {e}. Using hardcoded defaults.")
        return hardcoded_defaults

def generate_silence(duration_s, samplerate, temp_dir):
    """Generates a silence WAV file and returns its path."""
    if not samplerate:
        print("!! Error: Samplerate required to generate silence. Skipping.")
        return None
    print(f"\nGenerating {duration_s}s silence segment (SR: {samplerate} Hz)...")
    num_samples = int(duration_s * samplerate)
    silence_data = np.zeros(num_samples, dtype=np.float32)

    # Use mkstemp for unique file name, ensuring temp_dir is used
    temp_fd, temp_path = tempfile.mkstemp(suffix="_silence.wav", prefix="silence_", dir=temp_dir)
    os.close(temp_fd)
    try:
        sf.write(temp_path, silence_data, samplerate, subtype='PCM_16')
        print(f"-> Silence saved to {os.path.basename(temp_path)}")
        return temp_path
    except Exception as e:
        print(f"!! Error generating silence file: {e}")
        if os.path.exists(temp_path): os.remove(temp_path)
        return None

def concatenate_wavs(file_list, output_filename, target_samplerate):
    """Concatenates a list of WAV files into a single output file."""
    if not file_list:
         print("!! Error: No segment files provided for concatenation.")
         return False

    valid_files = [f for f in file_list if f and os.path.exists(f)]
    if not valid_files:
         print("!! Error: No valid files found in the list for concatenation.")
         return False

    if not target_samplerate:
        print("!! Warning: Target samplerate not provided for concatenation.")
        # Attempt to get samplerate from the first valid file
        try:
             info = sf.info(valid_files[0])
             target_samplerate = info.samplerate
             print(f"!! Using samplerate from first file ({os.path.basename(valid_files[0])}): {target_samplerate} Hz.")
        except Exception as e:
             print(f"!! Error: Could not determine target samplerate from first file: {e}")
             return False # Cannot proceed without a samplerate

    print(f"\nConcatenating {len(valid_files)} valid segments into {output_filename} (Target SR: {target_samplerate} Hz)...")
    output_data = []
    target_channels = 1 # Assume mono

    for i, filepath in enumerate(valid_files):
        print(f"-> Processing file {i+1}/{len(valid_files)}: {os.path.basename(filepath)}")
        try:
            # Check samplerate and resample if needed
            info = sf.info(filepath)
            data, sr = sf.read(filepath, dtype='float32')
            
            if info.samplerate != target_samplerate:
                print(f"-> Resampling {os.path.basename(filepath)} from {info.samplerate} Hz to {target_samplerate} Hz...")
                # Calculate resampling ratio
                ratio = target_samplerate / info.samplerate
                n_samples = int(len(data) * ratio)
                
                # Use scipy's resample function for high-quality resampling
                data = resample(data, n_samples)
                print(f"-> Resampling complete. New length: {len(data)/target_samplerate:.2f}s")

            # Convert to mono if necessary
            if info.channels == 2:
                print(f"-> Converting {os.path.basename(filepath)} to mono.")
                data = np.mean(data, axis=1)
            elif info.channels != 1:
                 print(f"!! Warning: Unexpected channel count ({info.channels}) in {os.path.basename(filepath)}. Attempting to process first channel.")
                 # Attempt to take the first channel if more than 2? Or skip? Let's try taking first.
                 if data.ndim > 1: data = data[:, 0]


            output_data.append(data)
            # Duration calculation here might be slightly off if we manipulated channels
            # Let's calculate duration based on output samples / target_sr
            print(f"-> Appended {os.path.basename(filepath)} ({len(data)/target_samplerate:.2f}s)")

        except Exception as e:
            print(f"!! Error reading/processing {os.path.basename(filepath)}: {e}")
            print("!! Skipping problematic file.")
            continue # Skip file on error

    if not output_data:
        print("!! No valid audio data to concatenate after processing.")
        return False

    print("Concatenating final audio data...")
    final_audio = np.concatenate(output_data)
    final_duration = len(final_audio) / target_samplerate
    print(f"Final audio length: {final_duration:.2f}s")

    try:
        print(f"Writing final audio to {output_filename}...")
        sf.write(output_filename, final_audio, target_samplerate, subtype='PCM_16')
        print(f"\n✅ Concatenated audio saved successfully to '{output_filename}' ({final_duration:.2f}s)")
        return True
    except Exception as e:
        print(f"!! Error writing final concatenated file '{output_filename}': {e}")
        return False