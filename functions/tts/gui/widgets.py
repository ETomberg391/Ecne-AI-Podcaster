import tkinter as tk
import os
import glob
from PIL import Image, ImageTk
import matplotlib.pyplot as plt
import numpy as np
import soundfile as sf
from tkinter import messagebox # For error messages in waveform update

# Import functions from other modules
from functions.tts.utils import load_voice_config

# Constants (re-defined for widgets, consider centralizing if truly global)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..', '..')) # Go up three levels from functions/tts/gui/
IMAGE_DIR = os.path.abspath(os.path.join(PROJECT_ROOT, "settings/images"))
MUSIC_DIR = os.path.abspath(os.path.join(PROJECT_ROOT, "settings/music"))
VOICE_DIR = os.path.abspath(os.path.join(PROJECT_ROOT, "settings/voices")) # Redundant, but kept for clarity if needed

PREVIEW_WIDTH = 300
HOST_GUEST_SCALE = 0.25
DEFAULT_BG = os.path.join(IMAGE_DIR, "background/Podcast_Background.png")
NO_MUSIC = "None"
NO_IMAGE = "None"

try:
    from pydub import AudioSegment
    pydub_available = True
except ImportError:
    pydub_available = False

def _get_default_closed_image(character_type):
    """Given a path (potentially in 'open'), find the corresponding path in 'closed'."""
    closed_dir = os.path.join(IMAGE_DIR, character_type, "closed")
    print(f"DEBUG get_default_closed_image ({character_type}): Searching in '{closed_dir}'")
    if not os.path.isdir(closed_dir):
        print(f"DEBUG get_default_closed_image: Closed dir not found: {closed_dir}")
        return NO_IMAGE
    image_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp')
    try:
        # Find first file matching extensions, sort to be deterministic
        closed_images = sorted([
            os.path.join(closed_dir, f)
            for f in os.listdir(closed_dir)
            if os.path.isfile(os.path.join(closed_dir, f)) and f.lower().endswith(image_extensions)
        ])
        print(f"DEBUG get_default_closed_image ({character_type}): Found potential closed images: {[os.path.basename(p) for p in closed_images]}")
        if closed_images:
            print(f"DEBUG get_default_closed_image ({character_type}): Using first found: {os.path.basename(closed_images[0])}")
            return closed_images[0] # Return the full path of the first found closed image
        else:
            print(f"DEBUG get_default_closed_image ({character_type}): No images found in {closed_dir}")
            return NO_IMAGE
    except Exception as e:
        print(f"DEBUG get_default_closed_image ({character_type}): Error listing dir {closed_dir}: {e}")
        return NO_IMAGE

def _load_and_resize_image(app_instance, image_path, target_width=None, target_height=None, scale_factor=None):
    """
    Loads an image, resizes it maintaining aspect ratio based on ONE target dimension
    (width OR height) or a scale_factor, and returns a PhotoImage object.
    If both target_width and target_height are provided, it resizes to exactly those dimensions (used for background).
    """
    if not image_path or image_path == NO_IMAGE or not os.path.exists(image_path):
        return None
    try:
        img = Image.open(image_path)
        original_width, original_height = img.size
        if original_height == 0: return None
        aspect_ratio = original_width / original_height

        # Determine target dimensions
        if target_width is not None and target_height is not None:
            # Exact resize (used for background fitting)
            new_width = target_width
            new_height = target_height
        elif scale_factor:
            new_width = int(original_width * scale_factor)
            new_height = int(original_height * scale_factor)
        elif target_width: # Resize based on width, calculate height
            new_width = target_width
            new_height = int(target_width / aspect_ratio)
        elif target_height: # Resize based on height, calculate width
            new_height = target_height
            new_width = int(target_height * aspect_ratio)
        else: # No resize needed
            new_width, new_height = original_width, original_height

        # Ensure minimum size
        new_width = max(1, new_width)
        new_height = max(1, new_height)

        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(img)
    except Exception as e:
        print(f"Error loading/resizing image {image_path}: {e}")
        return None

def _update_visual_preview(app_instance, bg_path=None, host_base_path=None, guest_base_path=None, speaker_context='none', force_redraw=False):
    """
    Updates the visual preview canvas with selected images.
    Derives 'open'/'closed' image paths based on speaker_context and base paths.
    Resizes images based on current canvas size.
    """
    if not app_instance.preview_canvas or not app_instance.preview_canvas.winfo_exists():
        return # Canvas not ready or destroyed

    # Get current canvas dimensions
    canvas_width = app_instance.preview_canvas.winfo_width()
    canvas_height = app_instance.preview_canvas.winfo_height()

    # If canvas size is invalid (e.g., during initial setup), don't draw yet
    if canvas_width <= 1 or canvas_height <= 1:
        return

    # Store current paths to check if redraw is needed
    current_bg = getattr(app_instance, '_current_preview_bg', None)
    current_host_base = getattr(app_instance, '_current_preview_host_base', None)
    current_guest_base = getattr(app_instance, '_current_preview_guest_base', None)
    current_context = getattr(app_instance, '_current_preview_context', None)

    # Only redraw if paths changed or forced
    if not force_redraw and bg_path == current_bg and host_base_path == current_host_base and guest_base_path == current_guest_base and speaker_context == current_context:
         return

    # Store the new base paths and context
    app_instance._current_preview_bg = bg_path
    app_instance._current_preview_host_base = host_base_path
    app_instance._current_preview_guest_base = guest_base_path
    app_instance._current_preview_context = speaker_context

    # --- Derive Host/Guest Paths based on Context using the helper ---
    host_path_to_load = host_base_path
    guest_path_to_load = guest_base_path

    # Helper for safe basename printing
    def safe_basename(path, default="None"):
        if path and path != NO_IMAGE:
            try:
                return os.path.basename(path)
            except TypeError: # Catch if it's somehow still not a path-like object
                return default
        return default

    print(f"  -> _update_visual_preview: Context='{speaker_context}', Host Base='{safe_basename(host_base_path)}', Guest Base='{safe_basename(guest_base_path)}'")

    if speaker_context == 'host_speaking':
        host_path_to_load = find_corresponding_open_image(host_base_path)
        print(f"    -> Attempting to find open image for HOST base: '{safe_basename(host_base_path)}'")

        print(f"  -> Context 'host_speaking'. Using HOST: {safe_basename(host_path_to_load)}, GUEST: {safe_basename(guest_path_to_load)}")
        print(f"    -> Resulting HOST path to load: '{safe_basename(host_path_to_load)}'")

    elif speaker_context == 'guest_speaking':
        guest_path_to_load = find_corresponding_open_image(guest_base_path)
        print(f"    -> Attempting to find open image for GUEST base: '{safe_basename(guest_base_path)}'")

        print(f"  -> Context 'guest_speaking'. Using HOST: {safe_basename(host_path_to_load)}, GUEST: {safe_basename(guest_path_to_load)}")
        print(f"    -> Resulting GUEST path to load: '{safe_basename(guest_path_to_load)}'")

    elif speaker_context in ['intro_outro', 'none']:
         # For intro/outro/none, always use the closed versions (base paths are already assigned)
         print(f"  -> Context '{speaker_context}'. Using HOST CLOSED ({safe_basename(host_path_to_load)}) and GUEST CLOSED ({safe_basename(guest_path_to_load)}) images.")

    # 1. Clear previous images and set background
    app_instance.preview_canvas.delete("all") # Clear all items
    app_instance.preview_canvas.config(bg='black') # Set background color for letterboxing
    app_instance.bg_photo_image = app_instance.host_photo_image = app_instance.guest_photo_image = None
    app_instance.bg_canvas_id = app_instance.host_canvas_id = app_instance.guest_canvas_id = None

    # 2. Calculate background dimensions to fit 16:9 within canvas
    target_bg_width = canvas_width
    target_bg_height = int(canvas_width * 9 / 16)

    if target_bg_height > canvas_height: # If calculated height is too tall, limit by height
        target_bg_height = canvas_height
        target_bg_width = int(canvas_height * 16 / 9)

    # Ensure dimensions are at least 1x1
    target_bg_width = max(1, target_bg_width)
    target_bg_height = max(1, target_bg_height)

    # 3. Load and resize background image using calculated dimensions
    app_instance.bg_photo_image = _load_and_resize_image(app_instance, bg_path, target_width=target_bg_width, target_height=target_bg_height)

    if app_instance.bg_photo_image:
        # Center the 16:9 background image within the canvas
        bg_x = max(0, (canvas_width - app_instance.bg_photo_image.width()) // 2)
        bg_y = max(0, (canvas_height - app_instance.bg_photo_image.height()) // 2)
        app_instance.bg_canvas_id = app_instance.preview_canvas.create_image(bg_x, bg_y, anchor=tk.NW, image=app_instance.bg_photo_image)
    else:
        # Draw grey background if no image path provided
         app_instance.preview_canvas.config(bg='grey') # Fallback if no image

    # 4. Load, resize, and display host/guest images (relative to canvas size)
    # Use the derived paths (host_path_to_load, guest_path_to_load)
    char_target_height = int(canvas_height * HOST_GUEST_SCALE * 1.5) # Slightly larger scale based on canvas height
    char_target_height = max(10, char_target_height) # Ensure minimum size

    # Host Image (bottom-left)
    app_instance.host_photo_image = _load_and_resize_image(app_instance, host_path_to_load, target_height=char_target_height)
    if app_instance.host_photo_image:
        host_x = 10 # Padding from left
        host_y = canvas_height - app_instance.host_photo_image.height() - 10 # Padding from bottom
        host_y = max(0, host_y) # Ensure y is not negative
        app_instance.host_canvas_id = app_instance.preview_canvas.create_image(host_x, host_y, anchor=tk.NW, image=app_instance.host_photo_image)

    # Guest Image (bottom-right)
    app_instance.guest_photo_image = _load_and_resize_image(app_instance, guest_path_to_load, target_height=char_target_height)
    if app_instance.guest_photo_image:
        guest_x = canvas_width - app_instance.guest_photo_image.width() - 10 # Padding from right
        guest_y = canvas_height - app_instance.guest_photo_image.height() - 10 # Padding from bottom
        guest_y = max(0, guest_y) # Ensure y is not negative
        guest_x = max(0, guest_x) # Ensure x is not negative
        app_instance.guest_canvas_id = app_instance.preview_canvas.create_image(guest_x, guest_y, anchor=tk.NW, image=app_instance.guest_photo_image)
def find_corresponding_open_image(base_path):
    """
    Helper function to find the corresponding 'open' image path given a 'closed' base path.
    Moved to module level for broader accessibility.
    """
    print(f"DEBUG find_corresponding_open_image: Called with base_path='{base_path}'")
    if not base_path or base_path == NO_IMAGE:
        print("DEBUG find_corresponding_open_image: base_path is None or NO_IMAGE, returning base_path.")
        return base_path # Return original if None or placeholder

    if not os.path.exists(base_path):
         print(f"DEBUG find_corresponding_open_image: base_path '{base_path}' does not exist, returning base_path.")
         return base_path # Return original if invalid path

    try:
        closed_dir = os.path.dirname(base_path)
        closed_filename = os.path.basename(base_path)
        closed_stem = os.path.splitext(closed_filename)[0] # Get filename without extension
        print(f"DEBUG find_corresponding_open_image: closed_dir='{closed_dir}', closed_stem='{closed_stem}'")

        if os.path.basename(closed_dir) != 'closed':
            print(f"DEBUG find_corresponding_open_image: Base path '{closed_filename}' not in a 'closed' directory, returning base_path.")
            return base_path # Not in a 'closed' directory, return original

        parent_dir = os.path.dirname(closed_dir)
        open_dir = os.path.join(parent_dir, 'open')
        print(f"DEBUG find_corresponding_open_image: Checking for open_dir='{open_dir}'")

        if not os.path.isdir(open_dir):
            print(f"  -> Corresponding 'open' directory not found: {open_dir}. Returning closed path.")
            return base_path # Fallback to closed

        print(f"DEBUG find_corresponding_open_image: Listing contents of open_dir='{open_dir}'")
        try:
            dir_contents = os.listdir(open_dir)
            print(f"DEBUG find_corresponding_open_image: Directory contents: {dir_contents}")
        except Exception as listdir_e:
            print(f"DEBUG find_corresponding_open_image: Error listing directory '{open_dir}': {listdir_e}")
            return base_path # Fallback on error

        # Find image files in the 'open' directory. Use the first one found if only one exists.
        image_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp')
        all_open_images = []
        for f in os.listdir(open_dir):
            if os.path.isfile(os.path.join(open_dir, f)) and f.lower().endswith(image_extensions):
                all_open_images.append(f)

        print(f"DEBUG find_corresponding_open_image: Found open images in '{open_dir}': {all_open_images}")

        if all_open_images:
            # Found one or more images, use the first one found
            open_image_path = os.path.join(open_dir, all_open_images[0])
            if len(all_open_images) > 1:
                 print(f"  -> Warning: Found multiple images in '{open_dir}': {all_open_images}. Using the first one: {os.path.basename(open_image_path)}")
            else:
                 print(f"  -> Found one open image: {os.path.basename(open_image_path)}. Using this path.")
            return open_image_path
        else: # len(all_open_images) == 0
            print(f"  -> No image files found in corresponding 'open' directory: {open_dir}. Returning closed image '{closed_filename}'.")
            return base_path # Fallback to closed if none found
    except Exception as e:
         print(f"  -> Error during find_corresponding_open_image logic: {e}. Returning closed path.")
         return base_path # Fallback on any unexpected error

    # --- Derive Host/Guest Paths based on Context using the helper ---
    host_path_to_load = host_base_path
    guest_path_to_load = guest_base_path

    # Helper for safe basename printing
    def safe_basename(path, default="None"):
        if path and path != NO_IMAGE:
            try:
                return os.path.basename(path)
            except TypeError: # Catch if it's somehow still not a path-like object
                return default
        return default

    print(f"  -> _update_visual_preview: Context='{speaker_context}', Host Base='{safe_basename(host_base_path)}', Guest Base='{safe_basename(guest_base_path)}'")

    if speaker_context == 'host_speaking':
        host_path_to_load = find_corresponding_open_image(host_base_path)
        print(f"    -> Attempting to find open image for HOST base: '{safe_basename(host_base_path)}'")

        print(f"  -> Context 'host_speaking'. Using HOST: {safe_basename(host_path_to_load)}, GUEST: {safe_basename(guest_path_to_load)}")
        print(f"    -> Resulting HOST path to load: '{safe_basename(host_path_to_load)}'")

    elif speaker_context == 'guest_speaking':
        guest_path_to_load = find_corresponding_open_image(guest_base_path)
        print(f"    -> Attempting to find open image for GUEST base: '{safe_basename(guest_base_path)}'")

        print(f"  -> Context 'guest_speaking'. Using HOST: {safe_basename(host_path_to_load)}, GUEST: {safe_basename(guest_path_to_load)}")
        print(f"    -> Resulting GUEST path to load: '{safe_basename(guest_path_to_load)}'")

    elif speaker_context in ['intro_outro', 'none']:
         # For intro/outro/none, always use the closed versions (base paths are already assigned)
         print(f"  -> Context '{speaker_context}'. Using HOST CLOSED ({safe_basename(host_path_to_load)}) and GUEST CLOSED ({safe_basename(guest_path_to_load)}) images.")

    # 1. Clear previous images and set background
    app_instance.preview_canvas.delete("all") # Clear all items
    app_instance.preview_canvas.config(bg='black') # Set background color for letterboxing
    app_instance.bg_photo_image = app_instance.host_photo_image = app_instance.guest_photo_image = None
    app_instance.bg_canvas_id = app_instance.host_canvas_id = app_instance.guest_canvas_id = None

    # 2. Calculate background dimensions to fit 16:9 within canvas
    target_bg_width = canvas_width
    target_bg_height = int(canvas_width * 9 / 16)

    if target_bg_height > canvas_height: # If calculated height is too tall, limit by height
        target_bg_height = canvas_height
        target_bg_width = int(canvas_height * 16 / 9)

    # Ensure dimensions are at least 1x1
    target_bg_width = max(1, target_bg_width)
    target_bg_height = max(1, target_bg_height)

    # 3. Load and resize background image using calculated dimensions
    app_instance.bg_photo_image = _load_and_resize_image(app_instance, bg_path, target_width=target_bg_width, target_height=target_bg_height)

    if app_instance.bg_photo_image:
        # Center the 16:9 background image within the canvas
        bg_x = max(0, (canvas_width - app_instance.bg_photo_image.width()) // 2)
        bg_y = max(0, (canvas_height - app_instance.bg_photo_image.height()) // 2)
        app_instance.bg_canvas_id = app_instance.preview_canvas.create_image(bg_x, bg_y, anchor=tk.NW, image=app_instance.bg_photo_image)
    else:
        # Draw grey background if no image path provided
         app_instance.preview_canvas.config(bg='grey') # Fallback if no image

    # 4. Load, resize, and display host/guest images (relative to canvas size)
    # Use the derived paths (host_path_to_load, guest_path_to_load)
    char_target_height = int(canvas_height * HOST_GUEST_SCALE * 1.5) # Slightly larger scale based on canvas height
    char_target_height = max(10, char_target_height) # Ensure minimum size

    # Host Image (bottom-left)
    app_instance.host_photo_image = _load_and_resize_image(app_instance, host_path_to_load, target_height=char_target_height)
    if app_instance.host_photo_image:
        host_x = 10 # Padding from left
        host_y = canvas_height - app_instance.host_photo_image.height() - 10 # Padding from bottom
        host_y = max(0, host_y) # Ensure y is not negative
        app_instance.host_canvas_id = app_instance.preview_canvas.create_image(host_x, host_y, anchor=tk.NW, image=app_instance.host_photo_image)

    # Guest Image (bottom-right)
    app_instance.guest_photo_image = _load_and_resize_image(app_instance, guest_path_to_load, target_height=char_target_height)
    if app_instance.guest_photo_image:
        guest_x = canvas_width - app_instance.guest_photo_image.width() - 10 # Padding from right
        guest_y = canvas_height - app_instance.guest_photo_image.height() - 10 # Padding from bottom
        guest_y = max(0, guest_y) # Ensure y is not negative
        guest_x = max(0, guest_x) # Ensure x is not negative
        app_instance.guest_canvas_id = app_instance.preview_canvas.create_image(guest_x, guest_y, anchor=tk.NW, image=app_instance.guest_photo_image)

def on_preview_resize(app_instance, event):
    """Called when the preview canvas is resized."""
    # Force redraw using stored paths
    # Retrieve the stored base paths and context
    bg_path = getattr(app_instance, '_current_preview_bg', None)
    host_base_path = getattr(app_instance, '_current_preview_host_base', None)
    guest_base_path = getattr(app_instance, '_current_preview_guest_base', None)
    speaker_context = getattr(app_instance, '_current_preview_context', 'none')

    _update_visual_preview(
        app_instance,
        bg_path=bg_path,
        host_base_path=host_base_path,
        guest_base_path=guest_base_path,
        speaker_context=speaker_context,
        force_redraw=True # Force redraw even if paths are same
    )

def clear_waveform(app_instance):
    """Clears the waveform plot and removes the player's progress line."""
    # Remove the progress line from the player if it exists
    if hasattr(app_instance, 'player') and app_instance.player and app_instance.player.progress_line and app_instance.player.progress_line in app_instance.ax.lines:
        try:
            app_instance.player.progress_line.remove()
            app_instance.player.progress_line = None
        except Exception as e:
            print(f"TTSDevGUI: Error removing progress line: {e}")

    # Clear the matplotlib axes
    app_instance.ax.clear()
    app_instance.ax.set_title("No Segment Selected")
    app_instance.ax.set_xlabel("Time (s)")
    app_instance.ax.set_ylabel("Amplitude")
    app_instance.ax.set_yticks([]) # Hide y-axis ticks when empty
    app_instance.ax.set_xticks([]) # Hide x-axis ticks when empty
    try:
        app_instance.waveform_canvas_agg.draw_idle() # Use draw_idle() for safer redrawing
    except Exception as e:
        print(f"TTSDevGUI: Error clearing waveform canvas: {e}")

def update_waveform(app_instance, file_path):
    """Reads an audio file and plots its waveform."""
    app_instance.ax.clear()
    if not file_path or not os.path.exists(file_path):
        print(f"TTSDevGUI: Waveform - File not found or invalid: {file_path}")
        clear_waveform(app_instance)
        return
    try:
        print(f"TTSDevGUI: Plotting waveform for {file_path}")
        with sf.SoundFile(file_path) as audio:
            data = audio.read(dtype='float32')
            samplerate = audio.samplerate
            duration = len(data) / samplerate
            time = np.linspace(0., duration, len(data))

            # If stereo, plot only the first channel for simplicity
            if data.ndim > 1:
                data = data[:, 0]

            app_instance.ax.plot(time, data, linewidth=0.5) # Thinner line for detail
            app_instance.ax.set_title(f"{os.path.basename(file_path)} ({duration:.2f}s)")
            app_instance.ax.set_xlabel("Time (s)")
            app_instance.ax.set_ylabel("Amplitude")
            # Set reasonable default y-limits, can be adjusted if needed
            max_abs_val = np.max(np.abs(data)) if len(data) > 0 else 1.0
            app_instance.ax.set_ylim(-max_abs_val * 1.1, max_abs_val * 1.1)
            app_instance.ax.grid(True) # Add grid
            app_instance.fig.tight_layout() # Adjust layout after plotting
            app_instance.waveform_canvas_agg.draw_idle() # Use draw_idle() for safer redrawing
    except Exception as e:
        print(f"TTSDevGUI: Error reading/plotting waveform: {e}")
        messagebox.showerror("Waveform Error", f"Could not display waveform.\n\nError: {e}")
        clear_waveform(app_instance) # Clear plot on error

def add_special_segment(app_instance, segment_type, data=None, original_index=-1):
    """Adds an Intro or Outro segment to the GUI, optionally populating from data."""
    if segment_type not in ['intro', 'outro']:
        return

    gui_index = app_instance.segment_listbox.size()
    display_name = "Intro" if segment_type == 'intro' else "Outro"

    if data:
        # Populate from existing data
        details = data.copy() # Work with a copy
        # When resuming, the correct original_index is passed in.
        details['original_index'] = original_index
        # Ensure image paths are not None, default to NO_IMAGE
        details['bg_image'] = details.get('bg_image') or NO_IMAGE
        details['host_image'] = details.get('host_image') or NO_IMAGE
        details['guest_image'] = details.get('guest_image') or NO_IMAGE
        print(f"TTSDevGUI: Adding resumed special segment: {display_name} (GUI Index {gui_index}, Original Index {original_index})")
    else:
        # Create new default data for a fresh run
        default_music_list = app_instance.intro_music_files if segment_type == 'intro' else app_instance.outro_music_files
        default_music = default_music_list[0] if default_music_list else NO_MUSIC
        default_bg = app_instance.background_files[0] if app_instance.background_files else NO_IMAGE
        default_host = _get_default_closed_image("host")
        default_guest = _get_default_closed_image("guest")

        details = {
            'type': segment_type,
            'text': f"[{display_name} Music]",
            'voice': None,
            'original_index': -1, # For fresh intros/outros, this doesn't map to all_segment_files yet
            'gain': 1.0,
            'bg_image': default_bg,
            'host_image': default_host,
            'guest_image': default_guest,
            'intro_music': default_music if segment_type == 'intro' else NO_MUSIC,
            'outro_music': default_music if segment_type == 'outro' else NO_MUSIC,
            'audio_path': default_music
        }
        print(f"TTSDevGUI: Added new special segment: {display_name} (GUI Index {gui_index})")

    app_instance.reviewable_segment_details[gui_index] = details
    # Map the GUI index to the true original_index in all_segment_files
    app_instance.gui_index_to_original_index[gui_index] = details['original_index']
    app_instance.segment_listbox.insert(tk.END, f"--- {display_name} ---")

def add_reviewable_segment(app_instance, original_index, file_path, text, voice, padding_ms=0, data=None):
    """Adds a speech segment to the GUI, optionally populating from data."""
    gui_index = app_instance.segment_listbox.size()

    if data:
        # Populate from existing data that's already processed
        details = data.copy() # Work with a copy
        details['original_index'] = original_index # Ensure the correct index is set
        # Ensure image paths are not None, default to NO_IMAGE
        details['bg_image'] = details.get('bg_image') or NO_IMAGE
        details['host_image'] = details.get('host_image') or NO_IMAGE
        details['guest_image'] = details.get('guest_image') or NO_IMAGE
        
        # If padding_ms is 0 in resumed data, set it to None to force recalculation in on_segment_select
        if details.get('padding_ms') == 0:
            details['padding_ms'] = None
        
        print(f"TTSDevGUI: Adding resumed speech segment: GUI Index {gui_index}, Original Index {original_index}, File: {details.get('audio_path')}")
    else:
        # Create new default data
        voice_config = load_voice_config(voice)
        default_gain = voice_config.get('gain_factor', 1.0)
        default_bg = app_instance.background_files[0] if app_instance.background_files else NO_IMAGE
        default_host_closed = _get_default_closed_image("host")
        default_guest_closed = _get_default_closed_image("guest")
        default_intro = next((f for f in app_instance.intro_music_files if f != NO_MUSIC), NO_MUSIC)
        default_outro = next((f for f in app_instance.outro_music_files if f != NO_MUSIC), NO_MUSIC)

        details = {
            'type': 'speech',
            'text': text,
            'voice': voice,
            'original_index': original_index,
            'gain': default_gain,
            'bg_image': default_bg,
            'host_image': default_host_closed,
            'guest_image': default_guest_closed,
            'intro_music': default_intro,
            'outro_music': default_outro,
            'audio_path': file_path,
            'padding_ms': padding_ms,
        }
        print(f"TTSDevGUI: Added new reviewable segment: GUI Index {gui_index}, Original Index {original_index}, File: {file_path}")

    app_instance.reviewable_segment_details[gui_index] = details
    app_instance.gui_index_to_original_index[gui_index] = original_index
    update_segment_display_name(app_instance, gui_index, details.get('audio_path'))

def update_segment_display_name(app_instance, gui_index, file_path=None):
    """Updates the text displayed in the listbox for a given GUI index."""
    details = app_instance.reviewable_segment_details.get(gui_index)
    if not details: return

    original_index = details['original_index']
    if file_path is None: # If file path not provided, get it from the main list
        if original_index < len(app_instance.all_segment_files):
            file_path = app_instance.all_segment_files[original_index]
        else:
            file_path = None # Cannot find file path

    duration = 0
    if file_path and os.path.exists(file_path):
        try:
            with sf.SoundFile(file_path) as audio:
                duration = len(audio) / audio.samplerate
        except Exception as e:
            print(f"Error getting duration for {file_path}: {e}")
            duration = -1 # Indicate error

    name = f"Segment {gui_index + 1} ({details['voice']})"
    if duration > 0:
        name += f" - {duration:.1f}s"
    elif duration < 0:
         name += " - Error"

    # Check if item exists before deleting/inserting
    if gui_index < app_instance.segment_listbox.size():
        app_instance.segment_listbox.delete(gui_index)
        app_instance.segment_listbox.insert(gui_index, name)
    elif gui_index == app_instance.segment_listbox.size():
        app_instance.segment_listbox.insert(tk.END, name)