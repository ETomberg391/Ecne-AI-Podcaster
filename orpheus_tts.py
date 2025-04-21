import requests
import argparse
import soundfile as sf
import io
import numpy as np
import os # Make sure os is imported
import os
import re
import tempfile
import yaml # Added for voice config loading
import wave # For checking properties, soundfile handles read/write
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, Canvas, PhotoImage
import sys # To check if running in GUI mode potentially
import threading
import time
import glob # For finding image/music files
from PIL import Image, ImageTk # For image display (pip install Pillow)
import nltk # For sentence tokenization (pip install nltk; run python -m nltk.downloader punkt once)
import subprocess
import shlex
try:
    from pydub import AudioSegment # For audio manipulation (pip install pydub)
    # Optional: Specify ffmpeg path if not in system PATH
    # AudioSegment.converter = "/path/to/ffmpeg"
    pydub_available = True
except ImportError:
    print("Warning: 'pydub' library not found. Intro/Outro functionality disabled. pip install pydub")
    pydub_available = False
import matplotlib
matplotlib.use('TkAgg') # Force TkAgg backend BEFORE importing pyplot

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from scipy.signal import butter, filtfilt # For high-pass filter
plt.style.use('seaborn-v0_8-darkgrid') # Optional: Use a nice style

# --- Constants ---
# Define Languages and Voices
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
ALL_VOICES = [voice for lang_voices in LANGUAGES_VOICES.values() for voice in lang_voices] # Flat list for validation if needed

SCRIPT_DIR = os.path.dirname(__file__) # Get the directory the script is in
IMAGE_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "settings/images"))
MUSIC_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "settings/music"))
VOICE_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "settings/voices")) # Define VOICE_DIR
os.makedirs(VOICE_DIR, exist_ok=True) # Ensure VOICE_DIR exists
PREVIEW_WIDTH = 300 # Width for the visual preview area
HOST_GUEST_SCALE = 0.25 # Scale factor for host/guest images
DEFAULT_BG = os.path.join(IMAGE_DIR, "background/Podcast_Background.png")
# Add "None" options for music/images
NO_MUSIC = "None"
NO_IMAGE = "None"

try:
    import pygame
    pygame.mixer.init() # Initialize the mixer
    if not pygame.mixer.get_init():
        print("Warning: Pygame mixer failed to initialize.")
        pygame = None # Treat as if pygame is not available
except ImportError:
    print("Warning: 'pygame' library not found. pip install pygame")
    pygame = None

class AudioPlayer(ttk.Frame):
    # Modify __init__ to accept waveform axes, canvas, and a redo command callback
    def __init__(self, parent, redo_command=None, waveform_ax=None, waveform_canvas_agg=None): # Added redo_command
        super().__init__(parent)
        self.redo_command = redo_command # Store the command
        self.waveform_ax = waveform_ax # Axes to draw progress line on
        self.waveform_canvas_agg = waveform_canvas_agg # Canvas to redraw (Renamed)
        self.progress_line = None # Line2D object for progress indicator

        self.current_file = None
        self.is_playing = False
        self.current_pos = 0 # Start time for playback (used for seeking)

        # Create player controls frame (packed first)
        self.controls_frame = ttk.Frame(self)
        self.controls_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=(5, 2)) # Pack controls at the top

        self.play_btn = ttk.Button(self.controls_frame, text="Play", width=5, command=self.toggle_play, state=tk.DISABLED) # Start disabled
        self.play_btn.pack(side=tk.LEFT, padx=2)

        self.stop_btn = ttk.Button(self.controls_frame, text="Stop", width=5, command=self.stop, state=tk.DISABLED) # Start disabled
        self.stop_btn.pack(side=tk.LEFT, padx=2)

        # Add Redo button here, initially disabled
        self.redo_btn = ttk.Button(self.controls_frame, text="Redo", width=5, command=self.redo_command, state=tk.DISABLED)
        self.redo_btn.pack(side=tk.LEFT, padx=2)

        # Progress bar and time labels frame (packed below controls)
        self.progress_frame = ttk.Frame(self)
        self.progress_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=(0, 5)) # Pack time label frame below controls

        self.time_var = tk.StringVar(value="00:00 / 00:00")
        self.time_label = ttk.Label(self.progress_frame, textvariable=self.time_var)
        # Pack time label within its own frame, aligned right
        self.time_label.pack(side=tk.RIGHT, padx=5)
# Removed ttk.Scale progress bar - interaction will be via waveform plot

        self.update_thread = None
        # self.seeking = False # No longer needed with direct waveform click seek

    def load_file(self, filepath):
        self.stop() # Stop any current playback
        self.current_file = None # Reset current file
        self.time_var.set("00:00 / 00:00") # Reset time label
        # self.progress.set(0) # Removed scale
        self.play_btn.configure(state=tk.DISABLED) # Disable buttons initially
        self.stop_btn.configure(state=tk.DISABLED)
        # self.progress.configure(state=tk.DISABLED) # Removed scale
        self._update_progress_line(0) # Reset progress line visually

        if not pygame:
            # No need for messagebox here, GUI should handle overall pygame check
            print("AudioPlayer: Pygame not available.")
            return False # Indicate failure

        if not filepath:
            print("AudioPlayer: No file path provided.")
            return False # Indicate failure

        print(f"AudioPlayer: Attempting to load audio file: {filepath}") # Debug print
        if not os.path.exists(filepath):
             print(f"AudioPlayer: Error - File does not exist: {filepath}")
             # Don't show messagebox here, let the calling GUI handle it
             return False # Indicate failure

        try:
            # Use soundfile first to get duration reliably
            # Use soundfile to get duration
            info = sf.info(filepath)
            duration = info.frames / info.samplerate
            print(f"AudioPlayer: Duration calculated via soundfile: {duration:.2f}s") # Debug print - Corrected indentation

            # Now load with pygame for playback
            pygame.mixer.music.load(filepath)
            print(f"AudioPlayer: Pygame loaded: {filepath}") # Debug print

            self.current_file = filepath # Set only after successful load
            self.duration = duration # Store duration
            # self.progress.configure(to=duration) # Removed scale
            self.update_time_label(0, duration)
            self.play_btn.configure(state=tk.NORMAL) # Enable controls
            self.stop_btn.configure(state=tk.NORMAL)
            # self.progress.configure(state=tk.NORMAL) # Removed scale
            self._update_progress_line(0) # Reset progress line visually
            return True # Indicate success

        except Exception as e:
            # messagebox.showerror("Error", f"Failed to load audio file:\n{filepath}\n\nError: {e}")
            print(f"AudioPlayer: Error loading audio file {filepath}: {e}") # Debug print
            self.current_file = None # Ensure file is None on error
            return False # Indicate failure

    def toggle_play(self):
        if not self.current_file or not pygame or not pygame.mixer.get_init():
            return

        if self.is_playing:
            try:
                pygame.mixer.music.pause()
                self.play_btn.configure(text="Play")
                self.is_playing = False # Update state after successful pause
            except Exception as e:
                 print(f"AudioPlayer: Error pausing music: {e}")
        else:
            try:
                # Check if music stream is valid before playing
                if not pygame.mixer.music.get_busy(): # If not busy, might need to reload/rewind
                     print("AudioPlayer: Music not busy, reloading and playing from start/seek pos.")
                     pygame.mixer.music.load(self.current_file) # Reload
                     pygame.mixer.music.play(start=self.current_pos) # Play from position
                else:
                     pygame.mixer.music.unpause() # If busy (i.e., paused), unpause

                self.play_btn.configure(text="Pause")
                self.is_playing = True # Update state after successful play/unpause

                # Start update thread if not running
                if not self.update_thread or not self.update_thread.is_alive():
                    self.update_thread = threading.Thread(target=self.update_progress, daemon=True)
                    self.update_thread.start()
            except Exception as e:
                messagebox.showerror("Playback Error", f"Error playing audio: {str(e)}")
                print(f"AudioPlayer: Error playing/unpausing music: {e}")
                self.is_playing = False # Reset state on error
                self.play_btn.configure(text="Play")
                return

    def stop(self):
        if pygame and pygame.mixer.get_init():
            try:
                pygame.mixer.music.stop()
                pygame.mixer.music.unload() # Explicitly unload
            except Exception as e:
                print(f"AudioPlayer: Error stopping/unloading music: {e}")

        self.is_playing = False
        self.current_pos = 0 # Reset position on stop
        self.play_btn.configure(text="Play")
        if self.current_file: # Only enable if a file was loaded
             self.play_btn.configure(state=tk.NORMAL)
        else:
             self.play_btn.configure(state=tk.DISABLED)
        # self.progress.set(0) # Removed scale
        self.update_time_label(0, getattr(self, 'duration', 0)) # Reset time label
        self._update_progress_line(0) # Reset progress line visually
        # Let's disable stop if no file is loaded.
        if self.current_file:
            self.stop_btn.configure(state=tk.NORMAL)
            # self.progress.configure(state=tk.NORMAL) # Removed scale
        else:
            self.stop_btn.configure(state=tk.DISABLED)
            # self.progress.configure(state=tk.DISABLED) # Removed scale


    # Removed start_seek and end_seek

    def seek_to_time(self, target_time):
        """Seeks playback to the specified time (in seconds)."""
        if not self.current_file or not pygame or not pygame.mixer.get_init():
            return
        if target_time < 0 or target_time > self.duration:
            print(f"AudioPlayer: Invalid seek time: {target_time:.2f}s")
            return

        print(f"AudioPlayer: Seek requested to {target_time:.2f}s")
        was_playing = self.is_playing # Remember if it was playing before seek
        self.is_playing = False # Temporarily set to false

        try:
            # Stop, load, and play from the seek position
            pygame.mixer.music.stop()
            pygame.mixer.music.load(self.current_file)
            pygame.mixer.music.play(start=target_time)
            self.current_pos = target_time # Update the starting position offset
            self.is_playing = True # Now set to playing
            self.play_btn.configure(text="Pause")
            self._update_progress_line(target_time) # Update line immediately

            # Restart update thread if needed
            if not self.update_thread or not self.update_thread.is_alive():
                print("AudioPlayer: Restarting update thread after seek.")
                self.update_thread = threading.Thread(target=self.update_progress, daemon=True)
                self.update_thread.start()

        except Exception as e:
            print(f"AudioPlayer: Error seeking and playing: {e}")
            messagebox.showerror("Seek Error", f"Error seeking audio: {e}")
            self.stop() # Reset state on seek error


    def update_progress(self):
        print("AudioPlayer: Starting update_progress loop.")
        while pygame and pygame.mixer.get_init() and self.current_file:
            # Check is_playing flag inside the loop, allows stop() to terminate it
            if not self.is_playing:
                 print("AudioPlayer: is_playing is False, breaking loop.")
                 break
            # if not self.seeking: # seeking flag removed
            try:
                # Removed redundant inner try
                    # get_pos returns time since playback *started*
                    current_playback_time = pygame.mixer.music.get_pos() / 1000.0

                    # Calculate actual position based on where we started playing from (current_pos)
                    # This accounts for seeks.
                    display_pos = self.current_pos + current_playback_time

                    if current_playback_time < 0: # Mixer might not be playing or error
                         if not pygame.mixer.music.get_busy(): # Check if stopped naturally
                              print("AudioPlayer: Playback finished (get_busy is False).")
                              # Need to ensure self.stop() is called to reset state properly
                              # Calling stop() here might cause issues if called from main thread too.
                              # Let's set is_playing to False and let the loop exit.
                              self.is_playing = False
                              # Schedule the UI update in the main thread if possible, or just set final state
                              self.play_btn.configure(text="Play")
                              # self.progress.set(0) # Removed scale
                              self.current_pos = 0
                              print("AudioPlayer: Exiting loop after playback finished.")
                              break # Exit loop
                         else:
                              # Still busy but negative time? Weird state, wait.
                              time.sleep(0.1)
                              continue

                    # Ensure display_pos doesn't exceed duration
                    # duration = self.progress.cget("to") # Removed scale, use self.duration
                    if display_pos >= self.duration: # Use >= to handle potential float inaccuracies
                        display_pos = self.duration
                        # If we reached duration, treat as finished
                        # Check get_busy() to see if playback actually stopped
                        if not pygame.mixer.music.get_busy():
                            self.is_playing = False
                            self.play_btn.configure(text="Play")
                            # self.progress.set(duration) # Removed scale
                            self.current_pos = 0
                            self._update_progress_line(0) # Reset line to start
                            self.update_time_label(0, self.duration) # Reset time label
                            print("AudioPlayer: Exiting loop after playback finished naturally.")
                            break # Exit loop

                    # Update progress line on waveform plot
                    self._update_progress_line(display_pos)
                    # Update time label
                    self.update_time_label(display_pos, self.duration)

            except Exception as e: # Corrected indentation
                # Catch specific pygame errors if possible, e.g., mixer not initialized
                if isinstance(e, pygame.error) and "mixer not initialized" in str(e):
                     print("AudioPlayer: Mixer became uninitialized during update.")
                     self.is_playing = False # Stop trying
                     break
                print(f"AudioPlayer: Error in update_progress: {type(e).__name__} - {e}")
                self.is_playing = False # Stop on other errors too
                break # Exit loop

            time.sleep(0.1) # Update every 100ms
        print("AudioPlayer: Exited update_progress loop.")


    def update_time_label(self, current, total):
         try:
            # Ensure total is non-negative for gmtime
            total = max(0, total)
            current = max(0, min(current, total)) # Clamp current between 0 and total
            current_str = time.strftime("%M:%S", time.gmtime(current))
            total_str = time.strftime("%M:%S", time.gmtime(total))
            self.time_var.set(f"{current_str} / {total_str}")
         except ValueError as e: # Handle potential negative time values briefly seen during seeks/stops
            print(f"AudioPlayer: ValueError updating time label: {e}. Current: {current}, Total: {total}")
            self.time_var.set("--:-- / --:--")


    def _update_progress_line(self, time_pos):
        """Updates the vertical progress line on the waveform plot."""
        if self.waveform_ax and self.waveform_canvas_agg: # Use renamed canvas
            # Ensure time_pos is within valid bounds if axes limits are set
            try:
                xlim = self.waveform_ax.get_xlim()
                time_pos = max(xlim[0], min(time_pos, xlim[1]))
            except Exception:
                 pass # Ignore if limits aren't set yet

            if self.progress_line is None:
                # Create the line if it doesn't exist
                # Use a check to prevent error if axes are cleared unexpectedly
                if self.waveform_ax.lines:
                     self.progress_line = self.waveform_ax.axvline(time_pos, color='r', linestyle='--', linewidth=1, label='_nolegend_')
                else:
                     self.progress_line = None # Cannot create line if axes are empty
                     return # Exit if axes are empty
            elif self.progress_line in self.waveform_ax.lines:
                # Update existing line's position only if it's still on the axes
                self.progress_line.set_xdata([time_pos, time_pos])
            else:
                 # Line was removed (e.g., by clear_waveform), recreate it
                 self.progress_line = self.waveform_ax.axvline(time_pos, color='r', linestyle='--', linewidth=1, label='_nolegend_')

            try:
                # Redraw the canvas to show the updated line
                self.waveform_canvas_agg.draw_idle() # Use draw_idle for efficiency (Use renamed canvas)
            except Exception as e:
                print(f"AudioPlayer: Error drawing progress line: {e}")


    def cleanup(self):
        """Stop playback and cleanup resources"""
        print("AudioPlayer: Cleanup called.")
        self.is_playing = False # Signal update thread to stop
        # Give thread a moment to exit?
        # time.sleep(0.15) # Small delay
        self.stop()


class TTSDevGUI:
    def __init__(self, api_host, api_port, speed, host_voice, guest_voice): # Added host_voice, guest_voice
        self.root = tk.Tk()
        self.root.title("TTS Development Interface - Visual & Audio")
        # Set initial size, but remove minsize to allow shrinking
        # self.root.minsize(1400, 900) # Removed minsize
        self.root.geometry("1200x800") # Start a bit smaller
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.api_host = api_host
        self.api_port = api_port
        self.speed = speed
        # Store host and guest voices for image logic
        self.host_voice = host_voice
        self.guest_voice = guest_voice
        self.final_structured_details = None # Initialize here

        # --- Load Image and Music Files ---
        self.background_files = [DEFAULT_BG] if os.path.exists(DEFAULT_BG) else []
        self.background_files += sorted(glob.glob(os.path.join(IMAGE_DIR, "background", "*.*")))

        # Load both 'open' and 'closed' images for host and guest
        def load_character_images(char_type):
            open_dir = os.path.join(IMAGE_DIR, char_type, "open")
            closed_dir = os.path.join(IMAGE_DIR, char_type, "closed")
            open_files = [NO_IMAGE] + sorted(glob.glob(os.path.join(open_dir, "*.*"))) if os.path.isdir(open_dir) else [NO_IMAGE]
            closed_files = [NO_IMAGE] + sorted(glob.glob(os.path.join(closed_dir, "*.*"))) if os.path.isdir(closed_dir) else [NO_IMAGE]
            # Filter out non-files, keeping NO_IMAGE
            open_files = sorted(list(set(f for f in open_files if f == NO_IMAGE or os.path.isfile(f))))
            closed_files = sorted(list(set(f for f in closed_files if f == NO_IMAGE or os.path.isfile(f))))
            return open_files, closed_files

        self.host_open_image_files, self.host_closed_image_files = load_character_images("host")
        self.guest_open_image_files, self.guest_closed_image_files = load_character_images("guest")

        self.intro_music_files = [NO_MUSIC] + sorted(glob.glob(os.path.join(MUSIC_DIR, "intro", "*.*")))
        self.outro_music_files = [NO_MUSIC] + sorted(glob.glob(os.path.join(MUSIC_DIR, "outro", "*.*")))

        # Ensure uniqueness and filter out non-files if necessary for background/music
        self.background_files = sorted(list(set(f for f in self.background_files if os.path.isfile(f))))
        self.intro_music_files = sorted(list(set(f for f in self.intro_music_files if f == NO_MUSIC or os.path.isfile(f))))
        self.outro_music_files = sorted(list(set(f for f in self.outro_music_files if f == NO_MUSIC or os.path.isfile(f))))

        # Create lists of basenames for display in Comboboxes
        self.background_names = [os.path.basename(f) for f in self.background_files]
        self.host_open_image_names = [os.path.basename(f) if f != NO_IMAGE else NO_IMAGE for f in self.host_open_image_files]
        self.host_closed_image_names = [os.path.basename(f) if f != NO_IMAGE else NO_IMAGE for f in self.host_closed_image_files]
        self.guest_open_image_names = [os.path.basename(f) if f != NO_IMAGE else NO_IMAGE for f in self.guest_open_image_files]
        self.guest_closed_image_names = [os.path.basename(f) if f != NO_IMAGE else NO_IMAGE for f in self.guest_closed_image_files]
        self.intro_music_names = [os.path.basename(f) if f != NO_MUSIC else NO_MUSIC for f in self.intro_music_files]
        self.outro_music_names = [os.path.basename(f) if f != NO_MUSIC else NO_MUSIC for f in self.outro_music_files]

        # Map names back to full paths (including all images)
        all_image_files = self.host_open_image_files + self.host_closed_image_files + self.guest_open_image_files + self.guest_closed_image_files
        self.name_to_path = {os.path.basename(f): f for f in self.background_files + all_image_files + self.intro_music_files + self.outro_music_files if f not in [NO_IMAGE, NO_MUSIC]}
        self.name_to_path[NO_IMAGE] = NO_IMAGE
        self.name_to_path[NO_MUSIC] = NO_MUSIC

        # Store the full sequence of files (speech and silence)
        self.all_segment_files = []
        # Store details only for the speech segments that are reviewable
        # Added keys: 'bg_image', 'host_image', 'guest_image', 'intro_music', 'outro_music'
        self.reviewable_segment_details = {}
        self.gui_index_to_original_index = {} # Maps GUI listbox index to index in all_segment_files

        # --- Initialize Tkinter Variables ---
        self.language_var = tk.StringVar()
        self.voice_var = tk.StringVar()
        self.progress_var = tk.DoubleVar(value=0)
        self.gain_var = tk.DoubleVar(value=1.0) # Variable for gain scale
        # New variables for image/music selection
        self.bg_image_var = tk.StringVar()
        self.host_image_var = tk.StringVar()
        self.guest_image_var = tk.StringVar()
        self.intro_music_var = tk.StringVar()
        self.outro_music_var = tk.StringVar()

        # New variables for processing options
        self.ffmpeg_enhancement_var = tk.BooleanVar(value=True) # For FFmpeg Checkbutton
        self.deesser_var = tk.BooleanVar(value=True) # For De-esser Checkbutton
        self.deesser_freq_var = tk.IntVar(value=5000) # For De-esser Frequency Spinbox
        self.trim_end_ms_var = tk.IntVar(value=120) # For Trim Spinbox/Entry
        self.padding_ms_var = tk.IntVar(value=0) # For Padding Spinbox/Entry
        # FFmpeg parameter variables
        self.nr_level_var = tk.IntVar(value=35) # afftdn nr
        self.compress_thresh_var = tk.DoubleVar(value=0.03) # sidechaincompress threshold
        self.compress_ratio_var = tk.IntVar(value=2) # sidechaincompress ratio
        self.norm_frame_len_var = tk.IntVar(value=20) # dynaudnorm f
        self.norm_gauss_size_var = tk.IntVar(value=15) # dynaudnorm g


# --- State Variables ---
        self.current_gui_selection = None # Index in the listbox
        self.temp_dir = None # Store temp dir for regeneration

        # --- UI Elements ---
        # Matplotlib waveform plot elements
        self.fig, self.ax = plt.subplots(figsize=(5, 1.5)) # Smaller figure size
        self.fig.tight_layout() # Adjust layout
        self.waveform_canvas_agg = None # Renamed from self.waveform_canvas to avoid clash
        self.player = None # Audio player instance
        self.preview_canvas = None # Tkinter Canvas for image preview
        self.bg_photo_image = None # PhotoImage references need to be kept
        self.host_photo_image = None
        self.guest_photo_image = None
        self.bg_canvas_id = None # Canvas item IDs
        self.host_canvas_id = None
        self.guest_canvas_id = None

        # Bind keyboard shortcuts
        self.root.bind('<Control-r>', lambda e: self.redo_segment())
        # self.root.bind('<space>', lambda e: self.player.toggle_play() if self.player else None) # Removed due to conflict with text editing
        self.root.bind('<Escape>', lambda e: self.player.stop() if self.player else None)

        # Create main layout
        self.create_widgets()

    def on_segment_select(self, event):
        # DEBUG: Print the state of the details dictionary at the start of selection
        print(f"DEBUG on_segment_select: Current details dict = {self.reviewable_segment_details}")
        selection = self.segment_listbox.curselection()
        if selection:
            gui_index = selection[0]
            # --- Add check to prevent processing if index is invalid ---
            if gui_index is None or gui_index < 0:
                 print(f"TTSDevGUI: Invalid selection index ({gui_index}), skipping.")
                 return
            # --- End check ---
            self.current_gui_selection = gui_index # Store 0-based GUI index
            print(f"TTSDevGUI: Selected listbox index {self.current_gui_selection}") # Debug print

            details = self.reviewable_segment_details.get(self.current_gui_selection)
            original_index = self.gui_index_to_original_index.get(self.current_gui_selection)

            # --- Reset UI elements ---
            print("DEBUG: Resetting UI elements...") # DEBUG
            self.selected_segment_label.config(text="No Segment Selected") # Reset title label
            self.text_display.config(state=tk.NORMAL) # Ensure editable before clearing
            self.text_display.delete(1.0, tk.END)
            self.language_var.set(LANGUAGES[0]) # Default to first language
            self.voice_var.set("") # Clear voice initially
            self.update_voice_dropdown() # Update voice dropdown based on default language
            self.bg_image_var.set("")
            self.host_image_var.set("")
            self.guest_image_var.set("")
            self.intro_music_var.set("")
            self.outro_music_var.set("")
            self.gain_var.set(1.0)
            self.ffmpeg_enhancement_var.set(True) # Reset processing options
            self.trim_end_ms_var.set(120)        # Reset processing options
            self.padding_ms_var.set(0)           # Reset processing options
            # Reset FFmpeg params vars
            self.nr_level_var.set(35)
            self.compress_thresh_var.set(0.03)
            self.compress_ratio_var.set(2)
            self.norm_frame_len_var.set(20)
            self.norm_gauss_size_var.set(15)
            self.player.load_file(None) # Clear player first
            self.clear_waveform()
            self._update_visual_preview(speaker_context='none') # Clear preview, context 'none'
            self._toggle_ffmpeg_params_visibility() # Ensure params frame visibility is correct

            # Default state: enable most things, disable music dropdowns
            self.text_display.config(state=tk.NORMAL)
            self.language_combo.config(state='readonly')
            self.voice_combo.config(state='readonly')
            # Grid the gain frame if it's not already visible
            if not self.gain_frame.grid_info():
                self.gain_frame.grid(**self.gain_frame_grid_config) # Show gain using grid
            if self.player: self.player.redo_btn.configure(state=tk.DISABLED) # Use player's button
            self.intro_music_combo.config(state=tk.DISABLED)
            self.outro_music_combo.config(state=tk.DISABLED)
            # Image dropdowns always enabled if images exist
            self.bg_combo.config(state='readonly' if self.background_names else tk.DISABLED)
            # Check if there are any actual image files loaded (more than just the NO_IMAGE placeholder)
            host_images_exist = len(self.host_open_image_files) > 1 or len(self.host_closed_image_files) > 1
            guest_images_exist = len(self.guest_open_image_files) > 1 or len(self.guest_closed_image_files) > 1
            self.host_img_combo.config(state='readonly' if host_images_exist else tk.DISABLED)
            self.guest_img_combo.config(state='readonly' if guest_images_exist else tk.DISABLED)

            # --- Update Selected Segment Title ---
            try:
                selected_name = self.segment_listbox.get(gui_index)
                self.selected_segment_label.config(text=f"Selected: {selected_name}")
            except tk.TclError:
                 self.selected_segment_label.config(text="Error getting segment name")


            # --- Populate UI based on selected segment type ---
            print("DEBUG: Checking details...") # DEBUG
            if details:
                segment_type = details.get('type', 'speech') # Default to speech if type missing
                print(f"DEBUG: Segment type: {segment_type}")

                # 1. Populate common elements (Text, BG Image)
                print("DEBUG: Populating text display...") # DEBUG
                text_to_insert = details.get('text', '[No Text]')
                print(f"DEBUG: Text content to insert: {repr(text_to_insert)}")

                print("DEBUG: Populating BG image dropdown var...") # DEBUG
                bg_base_path = details.get('bg_image', NO_IMAGE)
                self.bg_image_var.set(os.path.basename(bg_base_path) if bg_base_path != NO_IMAGE else NO_IMAGE)

                # --- Determine Speaker Context ---
                speaker_context = 'none' # Default
                voice = details.get('voice')
                if segment_type == 'speech':
                    if voice == self.host_voice:
                        speaker_context = 'host_speaking'
                    elif voice == self.guest_voice:
                        speaker_context = 'guest_speaking'
                elif segment_type in ['intro', 'outro']:
                    speaker_context = 'intro_outro'
                print(f"DEBUG: Speaker context determined: {speaker_context}")

                # --- Update Host/Guest Dropdowns based on Context ---
                host_base_path = details.get('host_image', NO_IMAGE) # This should be the 'closed' path
                guest_base_path = details.get('guest_image', NO_IMAGE) # This should be the 'closed' path

                # Determine which image lists and which specific image path to use based on context
                host_names_to_show = self.host_closed_image_names
                guest_names_to_show = self.guest_closed_image_names
                host_path_to_select = host_base_path # Default to closed
                guest_path_to_select = guest_base_path # Default to closed

                # Re-use the helper function from preview logic to find the correct *path* (open or closed)
                # This helper function is defined within _update_visual_preview, we need to access it or redefine it here.
                # For simplicity, let's redefine the core logic here or call the preview's helper if accessible.
                # Assuming find_corresponding_open_image is accessible or we redefine its core logic here.
                # Let's call the existing helper from _update_visual_preview for consistency.
                # NOTE: This requires find_corresponding_open_image to be defined either globally or as a class method.
                # Assuming it's defined within _update_visual_preview, we call that method's helper.
                # We'll adapt the logic directly here for clarity in the diff.

                def find_corresponding_open_image_for_select(base_path):
                    # Simplified version for selection logic - assumes helper exists in preview for full logic
                    print(f"DEBUG (select) find_corresponding_open_image: Called with base_path='{base_path}'")
                    if not base_path or base_path == NO_IMAGE or not os.path.exists(base_path): return base_path
                    try:
                        closed_dir = os.path.dirname(base_path)
                        if os.path.basename(closed_dir) != 'closed': return base_path
                        parent_dir = os.path.dirname(closed_dir)
                        open_dir = os.path.join(parent_dir, 'open')
                        if not os.path.isdir(open_dir): return base_path # Fallback to closed if open dir missing

                        image_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp')
                        all_open_images = []
                        for f in os.listdir(open_dir):
                            if os.path.isfile(os.path.join(open_dir, f)) and f.lower().endswith(image_extensions):
                                all_open_images.append(f)
                        if all_open_images:
                            open_image_path = os.path.join(open_dir, all_open_images[0]) # Use first found
                            print(f"    -> (select) Found open image: {os.path.basename(open_image_path)}")
                            return open_image_path
                        else:
                            return base_path # Fallback to closed if no open image found
                    except Exception as e:
                         print(f"    -> (select) Error finding open image: {e}. Returning closed path.")
                         return base_path # Fallback on error

                if speaker_context == 'host_speaking':
                    host_names_to_show = self.host_open_image_names
                    host_path_to_select = find_corresponding_open_image_for_select(host_base_path) # Find the open path
                    guest_names_to_show = self.guest_closed_image_names # Guest remains closed
                    guest_path_to_select = guest_base_path
                elif speaker_context == 'guest_speaking':
                    host_names_to_show = self.host_closed_image_names # Host remains closed
                    host_path_to_select = host_base_path
                    guest_names_to_show = self.guest_open_image_names
                    guest_path_to_select = find_corresponding_open_image_for_select(guest_base_path) # Find the open path
                # Else (intro/outro/none), keep defaults (closed lists, closed selections)

                # Get the basenames of the paths determined above for setting the variable
                host_name_to_select = os.path.basename(host_path_to_select) if host_path_to_select != NO_IMAGE else NO_IMAGE
                guest_name_to_select = os.path.basename(guest_path_to_select) if guest_path_to_select != NO_IMAGE else NO_IMAGE

                print(f"DEBUG: Host Dropdown: Values={host_names_to_show}, Select='{host_name_to_select}'")
                print(f"DEBUG: Guest Dropdown: Values={guest_names_to_show}, Select='{guest_name_to_select}'")

                # Update dropdown values (the list of options)
                self.host_img_combo['values'] = host_names_to_show
                self.guest_img_combo['values'] = guest_names_to_show

                # Update dropdown selections (the currently selected item)
                self.host_image_var.set(host_name_to_select)
                self.guest_image_var.set(guest_name_to_select)
                # --- End Dropdown Update ---


                print("DEBUG: Updating visual preview with context...") # DEBUG
                # Pass BASE paths (closed) and the determined context to preview
                self._update_visual_preview(bg_path=bg_base_path, host_base_path=host_base_path, guest_base_path=guest_base_path, speaker_context=speaker_context)

                # 2. Populate type-specific elements and configure UI state
                audio_path_to_load = details.get('audio_path') # Path to speech segment or selected music

                if segment_type == 'speech':
                    print("DEBUG: Configuring UI for SPEECH segment...")
                    # First ensure text display is enabled and ready for input
                    self.text_display.config(state=tk.NORMAL)
                    self.text_display.delete(1.0, tk.END)  # Clear any existing text
                    self.text_display.insert(tk.END, details.get('text', ''))
                    print(f"DEBUG: Text display populated with: {details.get('text', '')[:50]}...")

                    # Populate Language, Voice & Gain
                    # Try to find the language for the current voice
                    current_voice = details.get('voice', '')
                    current_language = LANGUAGES[0] # Default
                    for lang, voices in LANGUAGES_VOICES.items():
                        if current_voice in voices:
                            current_language = lang
                            break
                    self.language_var.set(current_language)
                    self.update_voice_dropdown() # Update voice options for the detected language
                    self.voice_var.set(current_voice) # Set the specific voice

                    self.gain_var.set(details.get('gain', 1.0))
                    self._update_gain_label_format()

                    # --- Load Voice-Specific Defaults from YAML ---
                    print(f"  Segment {self.current_gui_selection}: Loading UI defaults from config for voice '{voice}'.")
                    voice_config = load_voice_config(voice) # Load config for the current voice

                    # Use loaded config to set UI variables
                    default_gain = voice_config.get('gain_factor', 1.0)
                    default_trim_end_ms = voice_config.get('trim_end_ms', 120)
                    default_nr_level = voice_config.get('nr_level', 35)
                    default_compress_thresh = voice_config.get('compress_thresh', 0.03)
                    default_compress_ratio = voice_config.get('compress_ratio', 2)
                    default_norm_frame_len = voice_config.get('norm_frame_len', 20)
                    default_norm_gauss_size = voice_config.get('norm_gauss_size', 15)
                    default_deesser_freq = voice_config.get('deesser_freq', 5000)

                    # Set default enhancement toggles (these are NOT from YAML)
                    default_ffmpeg_enabled = True # Default FFmpeg ON
                    default_deesser_enabled = True if voice != 'leo' else False # Default De-esser ON, except for Leo

                    # Ensure default gauss size is odd (loaded from YAML)
                    if default_norm_gauss_size % 2 == 0:
                        default_norm_gauss_size -= 1

                    # --- Calculate Context-Aware Default Padding (Remains the same) ---
                    default_padding_ms = 0 # Default to 0 if last segment or error
                    next_gui_index = self.current_gui_selection + 1
                    if next_gui_index < self.segment_listbox.size(): # Check if next segment exists in listbox
                        next_details = self.reviewable_segment_details.get(next_gui_index)
                        if next_details:
                            next_segment_type = next_details.get('type')
                            if next_segment_type == 'speech':
                                next_voice = next_details.get('voice')
                                if voice == next_voice:
                                    default_padding_ms = 100 # Same speaker next
                                else:
                                    default_padding_ms = 750 # Different speaker next
                            else: # Next segment is intro/outro/etc.
                                default_padding_ms = 750 # Treat transition out of speech like speaker change
                        else:
                             # Should not happen if index is valid, but defensively set to 0
                             print(f"Warning: Could not get details for next GUI index {next_gui_index}")
                             default_padding_ms = 0
                    else: # This is the last segment in the listbox
                        default_padding_ms = 0
                    print(f"  Segment {self.current_gui_selection}: Calculated default padding: {default_padding_ms}ms")

                    # --- Populate processing options using loaded config and calculated padding ---
                    # User modifications will be saved back to details via handlers, but selection always resets to defaults from config/logic.
                    self.ffmpeg_enhancement_var.set(default_ffmpeg_enabled) # Set enhancement toggle default
                    self.deesser_var.set(default_deesser_enabled)         # Set de-esser toggle default

                    # Set UI variables from loaded config
                    self.gain_var.set(default_gain) # Set gain slider from config
                    self.trim_end_ms_var.set(default_trim_end_ms)
                    self.deesser_freq_var.set(default_deesser_freq)
                    self.nr_level_var.set(default_nr_level)
                    self.compress_thresh_var.set(default_compress_thresh)
                    self.compress_ratio_var.set(default_compress_ratio)
                    self.norm_frame_len_var.set(default_norm_frame_len)
                    self.norm_gauss_size_var.set(default_norm_gauss_size) # Already ensured odd above

                    # Set padding variable using calculated context-aware default
                    self.padding_ms_var.set(default_padding_ms) # Always use the calculated default padding

                    # Set initial state of de-esser frequency spinbox based on loaded TOGGLE states
                    self.deesser_freq_spinbox.configure(state='normal' if (default_ffmpeg_enabled and default_deesser_enabled) else 'disabled')

                    self._toggle_ffmpeg_params_visibility() # Show/hide params frame based on loaded ffmpeg_enabled toggle
                    # UI State: Disable music, enable speech-related and processing
                    self.intro_music_combo.config(state=tk.DISABLED)
                    self.outro_music_combo.config(state=tk.DISABLED)
                    self.text_display.config(state=tk.NORMAL)
                    self.language_combo.config(state='readonly')
                    self.voice_combo.config(state='readonly')
                    # Grid the gain frame if it's not already visible
                    if not self.gain_frame.grid_info():
                        self.gain_frame.grid(**self.gain_frame_grid_config) # Show gain using grid

                elif segment_type == 'intro':
                    print("DEBUG: Configuring UI for INTRO segment...")
                    # Populate Intro Music
                    intro_path = details.get('intro_music', NO_MUSIC)
                    self.intro_music_var.set(os.path.basename(intro_path) if intro_path != NO_MUSIC else NO_MUSIC)
                    audio_path_to_load = intro_path # Load the selected intro music
                    # UI State: Disable speech-related, enable intro music
                    self.text_display.config(state=tk.DISABLED)
                    self.language_combo.config(state=tk.DISABLED)
                    self.voice_combo.config(state=tk.DISABLED)
                    if self.gain_frame.grid_info(): self.gain_frame.grid_forget() # Hide gain using grid
                    if self.player: self.player.redo_btn.configure(state=tk.DISABLED) # Use player's button
                    self.intro_music_combo.config(state='readonly' if pydub_available and self.intro_music_names else tk.DISABLED)
                    self.outro_music_combo.config(state=tk.DISABLED)

                elif segment_type == 'outro':
                    print("DEBUG: Configuring UI for OUTRO segment...")
                    # Populate Outro Music
                    outro_path = details.get('outro_music', NO_MUSIC)
                    self.outro_music_var.set(os.path.basename(outro_path) if outro_path != NO_MUSIC else NO_MUSIC)
                    audio_path_to_load = outro_path # Load the selected outro music
                    # UI State: Disable speech-related, enable outro music
                    self.text_display.config(state=tk.DISABLED)
                    self.language_combo.config(state=tk.DISABLED)
                    self.voice_combo.config(state=tk.DISABLED)
                    if self.gain_frame.grid_info(): self.gain_frame.grid_forget() # Hide gain using grid
                    if self.player: self.player.redo_btn.configure(state=tk.DISABLED) # Use player's button
                    self.intro_music_combo.config(state=tk.DISABLED)
                    self.outro_music_combo.config(state='readonly' if pydub_available and self.outro_music_names else tk.DISABLED)

                # 3. Load Audio (Speech or Music)
                print(f"DEBUG: Preparing to load audio file: {audio_path_to_load}") # DEBUG
                if audio_path_to_load and audio_path_to_load not in [NO_MUSIC, NO_IMAGE]:
                    # Add explicit check for file existence
                    print(f"DEBUG: Attempting to load audio file path: {audio_path_to_load}") # Added print
                    if not os.path.exists(audio_path_to_load):
                        print(f"ERROR - File does not exist: {audio_path_to_load}")
                        messagebox.showerror("Load Error", f"Audio file not found:\n{audio_path_to_load}")
                    else:
                        print(f"DEBUG: Calling self.player.load_file({audio_path_to_load})...") # DEBUG
                        if self.player.load_file(audio_path_to_load): # This calls into AudioPlayer
                            print("DEBUG: Audio file loaded successfully.") # DEBUG
                            if segment_type == 'speech' and self.player: # Only enable redo for speech
                                self.player.redo_btn.configure(state=tk.NORMAL) # Use player's button
                            print("DEBUG: Updating waveform...") # DEBUG
                            # Restore waveform update call
                            self.update_waveform(audio_path_to_load) # This calls sf.SoundFile
                            print("DEBUG: Waveform updated.") # DEBUG
                        else:
                             # Loading failed, show error
                             messagebox.showerror("Load Error", f"Failed to load audio file:\n{audio_path_to_load}")
                             # Keep redo disabled, waveform/preview already cleared
                else:
                    print("DEBUG: No valid audio path to load.")
                    # Ensure waveform is clear if no audio
                    self.clear_waveform()

            else:
                 # Error case: Could not find details for the selected GUI index
                 print(f"TTSDevGUI: Error - Could not find details for GUI index {self.current_gui_selection}")
                 # UI elements are already cleared from the start of the 'if selection:' block



    def set_temp_dir(self, temp_dir):
        self.temp_dir = temp_dir

    def set_all_segment_files(self, all_files):
        self.all_segment_files = list(all_files) # Make a copy

    def on_closing(self):
        """Handle window close button"""
        print("TTSDevGUI: Closing window.")
        if self.player:
            self.player.cleanup()
        # Indicate cancellation by setting the final details to None
        self.final_structured_details = None
        self.root.quit() # Quit mainloop
        plt.close(self.fig) # Close matplotlib figure
        self.root.destroy() # Destroy window explicitly

    # --- New Helper Function for Image Loading/Resizing ---
    def _load_and_resize_image(self, image_path, target_width=None, scale_factor=None):
        """Loads an image, resizes it, and returns a PhotoImage object."""
        if not image_path or image_path == NO_IMAGE or not os.path.exists(image_path):
            return None
        try:
            img = Image.open(image_path)
            original_width, original_height = img.size

            if scale_factor:
                new_width = int(original_width * scale_factor)
                new_height = int(original_height * scale_factor)
            elif target_width:
                aspect_ratio = original_height / original_width
                new_width = target_width
                new_height = int(target_width * aspect_ratio)
            else: # No resize needed
                new_width, new_height = original_width, original_height

            # Ensure minimum size if scaled down too much
            new_width = max(1, new_width)
            new_height = max(1, new_height)

            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(img)
        except Exception as e:
            print(f"Error loading/resizing image {image_path}: {e}")
            return None

    # --- New Helper Function for Updating Visual Preview ---
    def _update_visual_preview(self, bg_path=None, host_base_path=None, guest_base_path=None, speaker_context='none', force_redraw=False):
        """
        Updates the visual preview canvas with selected images.
        Derives 'open'/'closed' image paths based on speaker_context and base paths.
        Resizes images based on current canvas size.
        """
        if not self.preview_canvas or not self.preview_canvas.winfo_exists():
            return # Canvas not ready or destroyed

        # Get current canvas dimensions
        canvas_width = self.preview_canvas.winfo_width()
        canvas_height = self.preview_canvas.winfo_height()

        # If canvas size is invalid (e.g., during initial setup), don't draw yet
        if canvas_width <= 1 or canvas_height <= 1:
            return

        # Store current paths to check if redraw is needed
        # IMPORTANT: Store BASE paths for comparison, not the potentially derived 'open' paths.
        current_bg = getattr(self, '_current_preview_bg', None)
        current_host_base = getattr(self, '_current_preview_host_base', None)
        current_guest_base = getattr(self, '_current_preview_guest_base', None)
        current_context = getattr(self, '_current_preview_context', None)

        # Only redraw if paths changed or forced
        if not force_redraw and bg_path == current_bg and host_base_path == current_host_base and guest_base_path == current_guest_base and speaker_context == current_context:
             return

        # Store the new base paths and context
        self._current_preview_bg = bg_path
        self._current_preview_host_base = host_base_path
        self._current_preview_guest_base = guest_base_path
        self._current_preview_context = speaker_context

        # --- Helper Function to Find Corresponding Open Image ---
        def find_corresponding_open_image(base_path):
            print(f"DEBUG find_corresponding_open_image: Called with base_path='{base_path}'") # DEBUG
            if not base_path or base_path == NO_IMAGE:
                print("DEBUG find_corresponding_open_image: base_path is None or NO_IMAGE, returning base_path.") # DEBUG
                return base_path # Return original if None or placeholder

            if not os.path.exists(base_path):
                 print(f"DEBUG find_corresponding_open_image: base_path '{base_path}' does not exist, returning base_path.") # DEBUG
                 return base_path # Return original if invalid path

            try:
                closed_dir = os.path.dirname(base_path)
                closed_filename = os.path.basename(base_path)
                closed_stem = os.path.splitext(closed_filename)[0] # Get filename without extension
                print(f"DEBUG find_corresponding_open_image: closed_dir='{closed_dir}', closed_stem='{closed_stem}'") # DEBUG

                if os.path.basename(closed_dir) != 'closed':
                    print(f"DEBUG find_corresponding_open_image: Base path '{closed_filename}' not in a 'closed' directory, returning base_path.") # DEBUG
                    return base_path # Not in a 'closed' directory, return original

                parent_dir = os.path.dirname(closed_dir)
                open_dir = os.path.join(parent_dir, 'open')
                parent_dir = os.path.dirname(closed_dir)
                open_dir = os.path.join(parent_dir, 'open')
                print(f"DEBUG find_corresponding_open_image: Checking for open_dir='{open_dir}'") # DEBUG

                if not os.path.isdir(open_dir):
                    print(f"  -> Corresponding 'open' directory not found: {open_dir}. Returning closed path.") # INFO line
                    return base_path # Fallback to closed

                print(f"DEBUG find_corresponding_open_image: Listing contents of open_dir='{open_dir}'") # ADDED LOGGING
                try:
                    dir_contents = os.listdir(open_dir)
                    print(f"DEBUG find_corresponding_open_image: Directory contents: {dir_contents}") # ADDED LOGGING
                except Exception as listdir_e:
                    print(f"DEBUG find_corresponding_open_image: Error listing directory '{open_dir}': {listdir_e}") # ADDED LOGGING
                    return base_path # Fallback on error

                # Find image files in the 'open' directory. Use the first one found if only one exists.
                image_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp')

                print(f"DEBUG find_corresponding_open_image: Checking for open_dir='{open_dir}'") # DEBUG

                if not os.path.isdir(open_dir):
                    print(f"  -> Corresponding 'open' directory not found: {open_dir}. Returning closed path.") # INFO line
                    return base_path # Fallback to closed

                # Find image files in the 'open' directory. Use the first one found if only one exists.
                image_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp')
                all_open_images = []
                for f in os.listdir(open_dir):
                    if os.path.isfile(os.path.join(open_dir, f)) and f.lower().endswith(image_extensions):
                        all_open_images.append(f)

                print(f"DEBUG find_corresponding_open_image: Found open images in '{open_dir}': {all_open_images}") # DEBUG

                if all_open_images:
                    # Found one or more images, use the first one found
                    open_image_path = os.path.join(open_dir, all_open_images[0])
                    if len(all_open_images) > 1:
                         print(f"  -> Warning: Found multiple images in '{open_dir}': {all_open_images}. Using the first one: {os.path.basename(open_image_path)}") # WARN line
                    else:
                         print(f"  -> Found one open image: {os.path.basename(open_image_path)}. Using this path.") # INFO line
                    return open_image_path
                else: # len(all_open_images) == 0
                    print(f"  -> No image files found in corresponding 'open' directory: {open_dir}. Returning closed image '{closed_filename}'.") # INFO line
                    return base_path # Fallback to closed if none found
            except Exception as e:
                 print(f"  -> Error during find_corresponding_open_image logic: {e}. Returning closed path.") # ERROR line
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

        print(f"  -> _update_visual_preview: Context='{speaker_context}', Host Base='{safe_basename(host_base_path)}', Guest Base='{safe_basename(guest_base_path)}'") # ADDED LOGGING

        if speaker_context == 'host_speaking':
            host_path_to_load = find_corresponding_open_image(host_base_path)
            print(f"    -> Attempting to find open image for HOST base: '{safe_basename(host_base_path)}'") # ADDED LOGGING

            print(f"  -> Context 'host_speaking'. Using HOST: {safe_basename(host_path_to_load)}, GUEST: {safe_basename(guest_path_to_load)}") # Use helper
            print(f"    -> Resulting HOST path to load: '{safe_basename(host_path_to_load)}'") # ADDED LOGGING

        elif speaker_context == 'guest_speaking':
            guest_path_to_load = find_corresponding_open_image(guest_base_path)
            print(f"    -> Attempting to find open image for GUEST base: '{safe_basename(guest_base_path)}'") # ADDED LOGGING

            print(f"  -> Context 'guest_speaking'. Using HOST: {safe_basename(host_path_to_load)}, GUEST: {safe_basename(guest_path_to_load)}") # Use helper
            print(f"    -> Resulting GUEST path to load: '{safe_basename(guest_path_to_load)}'") # ADDED LOGGING

        elif speaker_context in ['intro_outro', 'none']:
            # For intro/outro/none, always use the closed versions (base paths are already assigned)
             print(f"  -> Context '{speaker_context}'. Using HOST CLOSED ({safe_basename(host_path_to_load)}) and GUEST CLOSED ({safe_basename(guest_path_to_load)}) images.") # Use helper

        # 1. Clear previous images and set background
        self.preview_canvas.delete("all") # Clear all items
        self.preview_canvas.config(bg='black') # Set background color for letterboxing
        self.bg_photo_image = self.host_photo_image = self.guest_photo_image = None
        self.bg_canvas_id = self.host_canvas_id = self.guest_canvas_id = None

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
        self.bg_photo_image = self._load_and_resize_image(bg_path, target_width=target_bg_width, target_height=target_bg_height)

        if self.bg_photo_image:
            # Center the 16:9 background image within the canvas
            bg_x = max(0, (canvas_width - self.bg_photo_image.width()) // 2)
            bg_y = max(0, (canvas_height - self.bg_photo_image.height()) // 2)
            self.bg_canvas_id = self.preview_canvas.create_image(bg_x, bg_y, anchor=tk.NW, image=self.bg_photo_image)
        else:
            # Draw grey background if no image path provided
             self.preview_canvas.config(bg='grey') # Fallback if no image

        # 4. Load, resize, and display host/guest images (relative to canvas size)
        # Use the derived paths (host_path_to_load, guest_path_to_load)
        char_target_height = int(canvas_height * HOST_GUEST_SCALE * 1.5) # Slightly larger scale based on canvas height
        char_target_height = max(10, char_target_height) # Ensure minimum size

        # Host Image (bottom-left)
        self.host_photo_image = self._load_and_resize_image(host_path_to_load, target_height=char_target_height)
        if self.host_photo_image:
            host_x = 10 # Padding from left
            host_y = canvas_height - self.host_photo_image.height() - 10 # Padding from bottom
            host_y = max(0, host_y) # Ensure y is not negative
            self.host_canvas_id = self.preview_canvas.create_image(host_x, host_y, anchor=tk.NW, image=self.host_photo_image)

        # Guest Image (bottom-right)
        self.guest_photo_image = self._load_and_resize_image(guest_path_to_load, target_height=char_target_height)
        if self.guest_photo_image:
            guest_x = canvas_width - self.guest_photo_image.width() - 10 # Padding from right
            guest_y = canvas_height - self.guest_photo_image.height() - 10 # Padding from bottom
            guest_y = max(0, guest_y) # Ensure y is not negative
            guest_x = max(0, guest_x) # Ensure x is not negative
            self.guest_canvas_id = self.preview_canvas.create_image(guest_x, guest_y, anchor=tk.NW, image=self.guest_photo_image)

    # --- Updated Helper for Image Loading/Resizing ---
    def _load_and_resize_image(self, image_path, target_width=None, target_height=None, scale_factor=None):
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
            if original_height == 0: return None # Avoid division by zero
            aspect_ratio = original_width / original_height

            # --- Determine target dimensions ---
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

            # print(f"Resizing {os.path.basename(image_path)} from {original_width}x{original_height} to {new_width}x{new_height}")
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(img)
        except Exception as e:
            print(f"Error loading/resizing image {image_path}: {e}")
            return None

    # --- New Event Handler for Preview Resizing ---
    def on_preview_resize(self, event):
        """Called when the preview canvas is resized."""
        # Debounce or add delay if needed, but for now, redraw directly
        # print(f"DEBUG: on_preview_resize triggered. New size: {event.width}x{event.height}")
        # Force redraw using stored paths
        # Retrieve the stored base paths and context
        bg_path = getattr(self, '_current_preview_bg', None)
        host_base_path = getattr(self, '_current_preview_host_base', None)
        guest_base_path = getattr(self, '_current_preview_guest_base', None)
        speaker_context = getattr(self, '_current_preview_context', 'none')

        self._update_visual_preview(
            bg_path=bg_path,
            host_base_path=host_base_path,
            guest_base_path=guest_base_path,
            speaker_context=speaker_context,
            force_redraw=True # Force redraw even if paths are same
        )

    def create_widgets(self):
        # --- Configure Root Window Grid ---
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1) # Left frame column
        self.root.grid_columnconfigure(1, weight=3) # Right frame column (more space)

        # --- Left Panel (Segment List) ---
        left_frame = ttk.Frame(self.root)
        left_frame.grid(row=0, column=0, sticky='nsew', padx=5, pady=5)
        left_frame.grid_rowconfigure(1, weight=1) # Allow list_frame to expand vertically
        left_frame.grid_columnconfigure(0, weight=1) # Allow list_frame to expand horizontally

        ttk.Label(left_frame, text="Reviewable Segments:").grid(row=0, column=0, sticky='w', pady=(0, 2))

        # Frame for Listbox and Scrollbar
        list_frame = ttk.Frame(left_frame)
        list_frame.grid(row=1, column=0, sticky='nsew')
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
        scrollbar.grid(row=0, column=1, sticky='ns')

        self.segment_listbox = tk.Listbox(list_frame, width=30, yscrollcommand=scrollbar.set) # Reduced default width
        self.segment_listbox.grid(row=0, column=0, sticky='nsew')
        scrollbar.config(command=self.segment_listbox.yview)
        self.segment_listbox.bind('<<ListboxSelect>>', self.on_segment_select)

        # --- Right Panel (Main Container) ---
        right_main_frame = ttk.Frame(self.root)
        right_main_frame.grid(row=0, column=1, sticky='nsew', padx=5, pady=5)
        right_main_frame.grid_rowconfigure(0, weight=1) # Allow row to expand vertically
        right_main_frame.grid_columnconfigure(0, weight=3) # Controls frame (more weight)
        right_main_frame.grid_columnconfigure(1, weight=1) # Preview frame (less weight)

        # --- Right-Left Sub-panel (Controls, Text, Waveform, Player) ---
        right_left_frame = ttk.Frame(right_main_frame)
        right_left_frame.grid(row=0, column=0, sticky='nsew', padx=(0, 5))
        # Configure rows for expansion
        right_left_frame.grid_columnconfigure(0, weight=1) # Allow content to expand horizontally
        right_left_frame.grid_rowconfigure(1, weight=2)  # Text Display row
        right_left_frame.grid_rowconfigure(3, weight=3)  # Waveform row

        # --- Right-Right Sub-panel (Visual Preview) ---
        right_right_frame = ttk.Frame(right_main_frame)
        right_right_frame.grid(row=0, column=1, sticky='nsew', padx=(5, 0))
        # Let the canvas determine the height, don't give the row extra weight
        right_right_frame.grid_rowconfigure(0, weight=0) # Label row
        right_right_frame.grid_rowconfigure(1, weight=0) # Canvas row should NOT expand vertically beyond its needs
        right_right_frame.grid_columnconfigure(0, weight=1) # Allow canvas to expand horizontally

        # --- Create Widgets in Order (using grid) ---

        # 0. Visual Preview (in right_right_frame)
        ttk.Label(right_right_frame, text="Visual Preview:").grid(row=0, column=0, sticky='w', pady=(0, 2))
        # Removed fixed size, will resize with frame
        self.preview_canvas = Canvas(right_right_frame, bg='grey', borderwidth=1, relief="sunken")
        self.preview_canvas.grid(row=1, column=0, sticky='new', pady=5) # Changed sticky to 'new'
        # Bind configure event to handle resizing
        self.preview_canvas.bind("<Configure>", self.on_preview_resize)
        # Initialize preview area - Trigger initial draw after a short delay
        self.root.after(100, lambda: self.on_preview_resize(None)) # Use lambda to avoid passing event object

        # --- Widgets in right_left_frame ---
        current_row = 0

        # Title label for selected segment
        self.selected_segment_label = ttk.Label(right_left_frame, text="No Segment Selected", font=('Helvetica', 12, 'bold'))
        self.selected_segment_label.grid(row=current_row, column=0, sticky='w', pady=(5, 2))
        current_row += 1

        # 1. Text Display
        # Label moved above for clarity
        # ttk.Label(right_left_frame, text="Segment Text:").grid(row=current_row, column=0, sticky='w')
        # current_row += 1 # Increment row for the label
        self.text_display = scrolledtext.ScrolledText(right_left_frame, height=8, wrap=tk.WORD) # Reduced default height
        self.text_display.grid(row=current_row, column=0, sticky='nsew', pady=5)
        current_row += 1

        # 2. Selection Frame (Voice, Images, Music, Processing)
        selection_frame = ttk.LabelFrame(right_left_frame, text="Segment Configuration")
        selection_frame.grid(row=current_row, column=0, sticky='ew', pady=5)
        selection_frame.grid_columnconfigure(1, weight=1) # Allow comboboxes/entries to expand
        current_row += 1
        sel_row = 0 # Internal row counter for selection_frame

        # 2a. Language Selector
        ttk.Label(selection_frame, text="Language:", width=10).grid(row=sel_row, column=0, sticky='w', padx=5, pady=2)
        self.language_combo = ttk.Combobox(selection_frame, textvariable=self.language_var,
                                           values=LANGUAGES, state='readonly')
        self.language_combo.grid(row=sel_row, column=1, sticky='ew', padx=5, pady=2)
        self.language_combo.bind('<<ComboboxSelected>>', self.handle_language_change)
        sel_row += 1

        # 2b. Voice Selector
        ttk.Label(selection_frame, text="Voice:", width=10).grid(row=sel_row, column=0, sticky='w', padx=5, pady=2)
        self.voice_combo = ttk.Combobox(selection_frame, textvariable=self.voice_var,
                                      values=[], state='readonly') # Values set dynamically
        self.voice_combo.grid(row=sel_row, column=1, sticky='ew', padx=5, pady=2)
        self.voice_combo.bind('<<ComboboxSelected>>', self.handle_voice_change)
        sel_row += 1 # Increment row after voice combo

        # 2c. Background Image Selector
        ttk.Label(selection_frame, text="Background:", width=10).grid(row=sel_row, column=0, sticky='w', padx=5, pady=2)
        self.bg_combo = ttk.Combobox(selection_frame, textvariable=self.bg_image_var,
                                     values=self.background_names, state='readonly') # Removed width
        self.bg_combo.grid(row=sel_row, column=1, sticky='ew', padx=5, pady=2)
        self.bg_combo.bind('<<ComboboxSelected>>', self.handle_bg_change)
        sel_row += 1 # Increment row after bg combo

        # 2d. Host Image Selector
        ttk.Label(selection_frame, text="Host Img:", width=10).grid(row=sel_row, column=0, sticky='w', padx=5, pady=2)
        self.host_img_combo = ttk.Combobox(selection_frame, textvariable=self.host_image_var,
                                           values=self.host_closed_image_names, state='readonly') # Start with closed names
        self.host_img_combo.grid(row=sel_row, column=1, sticky='ew', padx=5, pady=2)
        self.host_img_combo.bind('<<ComboboxSelected>>', self.handle_host_img_change)
        sel_row += 1 # Increment row after host img combo

        # 2e. Guest Image Selector
        ttk.Label(selection_frame, text="Guest Img:", width=10).grid(row=sel_row, column=0, sticky='w', padx=5, pady=2)
        self.guest_img_combo = ttk.Combobox(selection_frame, textvariable=self.guest_image_var,
                                            values=self.guest_closed_image_names, state='readonly') # Start with closed names
        self.guest_img_combo.grid(row=sel_row, column=1, sticky='ew', padx=5, pady=2)
        self.guest_img_combo.bind('<<ComboboxSelected>>', self.handle_guest_img_change)
        sel_row += 1 # Increment row after guest img combo

        # 2f. Intro Music Selector
        ttk.Label(selection_frame, text="Intro Music:", width=10).grid(row=sel_row, column=0, sticky='w', padx=5, pady=2)
        self.intro_music_combo = ttk.Combobox(selection_frame, textvariable=self.intro_music_var,
                                              values=self.intro_music_names, state='readonly') # Removed width
        self.intro_music_combo.grid(row=sel_row, column=1, sticky='ew', padx=5, pady=2)
        self.intro_music_combo.bind('<<ComboboxSelected>>', self.handle_intro_music_change)
        if not pydub_available: self.intro_music_combo.config(state=tk.DISABLED)
        sel_row += 1 # Increment row after intro music combo

        # 2g. Outro Music Selector
        ttk.Label(selection_frame, text="Outro Music:", width=10).grid(row=sel_row, column=0, sticky='w', padx=5, pady=2)
        self.outro_music_combo = ttk.Combobox(selection_frame, textvariable=self.outro_music_var,
                                              values=self.outro_music_names, state='readonly') # Removed width
        self.outro_music_combo.grid(row=sel_row, column=1, sticky='ew', padx=5, pady=2)
        self.outro_music_combo.bind('<<ComboboxSelected>>', self.handle_outro_music_change)
        if not pydub_available: self.outro_music_combo.config(state=tk.DISABLED)
        sel_row += 1 # Increment row after outro music combo

        # --- Audio Processing Options (within selection_frame) ---
        processing_frame = ttk.LabelFrame(selection_frame, text="Audio Processing")
        # Span across columns in selection_frame
        processing_frame.grid(row=sel_row, column=0, columnspan=2, sticky='ew', padx=5, pady=(10, 2))
        processing_frame.grid_columnconfigure(0, weight=0) # Label column
        processing_frame.grid_columnconfigure(1, weight=1) # Control column
        sel_row += 1
        proc_row = 0 # Internal row counter for processing_frame

        # 2h. FFmpeg Enhancement Toggle
        self.ffmpeg_check = ttk.Checkbutton(processing_frame, text="Apply FFmpeg Enhancement (NR, Norm, De-ess)",
                                             variable=self.ffmpeg_enhancement_var,
                                             command=self.handle_ffmpeg_change)
        self.ffmpeg_check.grid(row=proc_row, column=0, columnspan=2, sticky='w', padx=5, pady=(2,0))
        proc_row += 1

        # De-esser Frame (within processing_frame)
        deesser_frame = ttk.Frame(processing_frame)
        deesser_frame.grid(row=proc_row, column=0, columnspan=2, sticky='ew', padx=5, pady=2)
        deesser_frame.grid_columnconfigure(2, weight=1) # Allow spinbox to potentially expand if needed
        proc_row += 1

        self.deesser_check = ttk.Checkbutton(deesser_frame, text="Apply De-esser",
                                        variable=self.deesser_var,
                                        command=self.handle_deesser_change)
        self.deesser_check.grid(row=0, column=0, sticky='w', padx=5)

        ttk.Label(deesser_frame, text="Frequency (Hz):").grid(row=0, column=1, sticky='w', padx=(10, 2))
        self.deesser_freq_spinbox = ttk.Spinbox(deesser_frame, from_=3000, to=10000, increment=500,
                                              textvariable=self.deesser_freq_var, width=6,
                                              command=self.handle_ffmpeg_param_change, wrap=True)
        self.deesser_freq_var.trace_add("write", self.handle_ffmpeg_param_change_trace)
        self.deesser_freq_spinbox.grid(row=0, column=2, sticky='w', padx=5)

        # 2i. Trim End Control
        trim_frame = ttk.Frame(processing_frame)
        trim_frame.grid(row=proc_row, column=0, columnspan=2, sticky='ew', padx=5, pady=2)
        trim_frame.grid_columnconfigure(1, weight=1)
        proc_row += 1
        ttk.Label(trim_frame, text="Trim End (ms):", width=15).grid(row=0, column=0, sticky='w', padx=5)
        self.trim_spinbox = ttk.Spinbox(trim_frame, from_=0, to=1000, increment=10,
                                        textvariable=self.trim_end_ms_var, width=6,
                                        command=self.handle_trim_change, wrap=True)
        self.trim_end_ms_var.trace_add("write", self.handle_trim_change_trace)
        self.trim_spinbox.grid(row=0, column=1, sticky='w', padx=5)

        # 2j. Padding Control
        padding_frame = ttk.Frame(processing_frame)
        padding_frame.grid(row=proc_row, column=0, columnspan=2, sticky='ew', padx=5, pady=2)
        padding_frame.grid_columnconfigure(1, weight=1)
        proc_row += 1
        ttk.Label(padding_frame, text="End Padding (ms):", width=15).grid(row=0, column=0, sticky='w', padx=5)
        self.padding_spinbox = ttk.Spinbox(padding_frame, from_=0, to=5000, increment=50,
                                           textvariable=self.padding_ms_var, width=6,
                                           command=self.handle_padding_change, wrap=True)
        self.padding_ms_var.trace_add("write", self.handle_padding_change_trace)
        self.padding_spinbox.grid(row=0, column=1, sticky='w', padx=5)

        # Separator
        ttk.Separator(processing_frame, orient=tk.HORIZONTAL).grid(row=proc_row, column=0, columnspan=2, sticky='ew', pady=(8, 4), padx=5)
        proc_row += 1

        # --- FFmpeg Parameter Controls (within processing_frame) ---
        self.ffmpeg_params_frame = ttk.Frame(processing_frame)
        # Grid this frame dynamically in _toggle_ffmpeg_params_visibility
        self.ffmpeg_params_frame_grid_config = {'row': proc_row, 'column': 0, 'columnspan': 2, 'sticky': 'ew', 'padx': 5, 'pady': 2}
        # proc_row += 1 # Increment row after placing the frame container

        ff_row = 0 # Internal row counter for ffmpeg_params_frame
        self.ffmpeg_params_frame.grid_columnconfigure(1, weight=1) # Allow controls to align

        # Noise Reduction Level
        ttk.Label(self.ffmpeg_params_frame, text="NR Level (0-97):", width=18).grid(row=ff_row, column=0, sticky='w', padx=5, pady=1)
        self.nr_spinbox = ttk.Spinbox(self.ffmpeg_params_frame, from_=0, to=97, increment=1, textvariable=self.nr_level_var, width=6, command=self.handle_ffmpeg_param_change, wrap=True)
        self.nr_level_var.trace_add("write", self.handle_ffmpeg_param_change_trace)
        self.nr_spinbox.grid(row=ff_row, column=1, sticky='w', padx=5, pady=1)
        ff_row += 1

        # Compressor Threshold
        ttk.Label(self.ffmpeg_params_frame, text="Comp Thresh (0.001-1):", width=18).grid(row=ff_row, column=0, sticky='w', padx=5, pady=1)
        self.compress_thresh_entry = ttk.Entry(self.ffmpeg_params_frame, textvariable=self.compress_thresh_var, width=6)
        self.compress_thresh_var.trace_add("write", self.handle_ffmpeg_param_change_trace)
        self.compress_thresh_entry.grid(row=ff_row, column=1, sticky='w', padx=5, pady=1)
        ff_row += 1

        # Compressor Ratio
        ttk.Label(self.ffmpeg_params_frame, text="Comp Ratio (1-20):", width=18).grid(row=ff_row, column=0, sticky='w', padx=5, pady=1)
        self.compress_ratio_spinbox = ttk.Spinbox(self.ffmpeg_params_frame, from_=1, to=20, increment=1, textvariable=self.compress_ratio_var, width=6, command=self.handle_ffmpeg_param_change, wrap=True)
        self.compress_ratio_var.trace_add("write", self.handle_ffmpeg_param_change_trace)
        self.compress_ratio_spinbox.grid(row=ff_row, column=1, sticky='w', padx=5, pady=1)
        ff_row += 1

        # Normalization Frame Length
        ttk.Label(self.ffmpeg_params_frame, text="Norm Frame (10-8000):", width=18).grid(row=ff_row, column=0, sticky='w', padx=5, pady=1)
        self.norm_frame_spinbox = ttk.Spinbox(self.ffmpeg_params_frame, from_=10, to=8000, increment=10, textvariable=self.norm_frame_len_var, width=6, command=self.handle_ffmpeg_param_change, wrap=True)
        self.norm_frame_len_var.trace_add("write", self.handle_ffmpeg_param_change_trace)
        self.norm_frame_spinbox.grid(row=ff_row, column=1, sticky='w', padx=5, pady=1)
        ff_row += 1

        # Normalization Gauss Size
        ttk.Label(self.ffmpeg_params_frame, text="Norm Gauss (3-301):", width=18).grid(row=ff_row, column=0, sticky='w', padx=5, pady=1)
        self.norm_gauss_spinbox = ttk.Spinbox(self.ffmpeg_params_frame, from_=3, to=301, increment=2, textvariable=self.norm_gauss_size_var, width=6, command=self.handle_ffmpeg_param_change, wrap=True)
        self.norm_gauss_size_var.trace_add("write", self.handle_ffmpeg_param_change_trace)
        self.norm_gauss_spinbox.grid(row=ff_row, column=1, sticky='w', padx=5, pady=1)
        ff_row += 1

        # Initial state based on the main checkbox
        self._toggle_ffmpeg_params_visibility() # This will grid/grid_forget the frame

        # 3. Waveform Plot Area
        self.waveform_canvas_agg = FigureCanvasTkAgg(self.fig, master=right_left_frame)
        self.waveform_canvas_agg.mpl_connect('button_press_event', self.on_waveform_click)
        self.waveform_canvas_widget = self.waveform_canvas_agg.get_tk_widget()
        self.waveform_canvas_widget.grid(row=current_row, column=0, sticky='nsew', pady=5)
        current_row += 1

        # 4. Audio Player Instance
        self.player = AudioPlayer(right_left_frame, redo_command=self.redo_segment, waveform_ax=self.ax, waveform_canvas_agg=self.waveform_canvas_agg)
        self.player.grid(row=current_row, column=0, sticky='ew', pady=(0, 5))
        current_row += 1

        # 5. Gain Control Frame (gridded dynamically later)
        self.gain_frame = ttk.Frame(right_left_frame)
        self.gain_frame_grid_config = {'row': current_row, 'column': 0, 'sticky': 'ew', 'pady': 5}
        # Don't increment current_row here, gain frame shares row space conceptually

        self.gain_label = ttk.Label(self.gain_frame, text="Volume Gain:")
        self.gain_label.pack(side=tk.LEFT, padx=5) # Use pack within this simple frame
        self.gain_scale = ttk.Scale(self.gain_frame, from_=0.5, to=3.0, orient=tk.HORIZONTAL, variable=self.gain_var, command=self.handle_gain_change) # Removed length
        self.gain_scale.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.gain_value_label = ttk.Label(self.gain_frame, textvariable=self.gain_var, width=4)
        self.gain_var.trace_add("write", self._update_gain_label_format)
        self.gain_value_label.pack(side=tk.LEFT, padx=5)
        # Initial gridding/hiding is handled in on_segment_select

        # 6. Keyboard shortcuts hint
        self.shortcuts_label = ttk.Label(right_left_frame, text="Keyboard Shortcuts:")
        self.shortcuts_label.grid(row=current_row + 1, column=0, sticky='w', pady=(10,0)) # Place below potential gain frame row
        ttk.Label(right_left_frame, text="Ctrl+R: Redo  |  Esc: Stop Playback", foreground='gray50').grid(row=current_row + 2, column=0, sticky='w')
        ttk.Separator(right_left_frame, orient=tk.HORIZONTAL).grid(row=current_row + 3, column=0, sticky='ew', pady=(5,10))
        current_row += 4 # Increment past gain row and shortcut rows

        # 7. Progress bar (gridded dynamically later)
        self.progress_bar = ttk.Progressbar(right_left_frame, mode='indeterminate', variable=self.progress_var)
        self.progress_bar_grid_config = {'row': current_row, 'column': 0, 'sticky': 'ew', 'pady': 5}
        # Don't increment current_row

        # 8. Bottom Button Frame
        bottom_button_frame = ttk.Frame(right_left_frame)
        # Place at a high row number to ensure it's at the bottom, or manage rows better
        bottom_button_frame.grid(row=100, column=0, sticky='sew', pady=10) # Use a high row index or manage rows
        right_left_frame.grid_rowconfigure(100, weight=0) # Ensure bottom row doesn't expand excessively
        bottom_button_frame.grid_columnconfigure(0, weight=1) # Allow space before button

        self.finalize_btn = ttk.Button(bottom_button_frame, text="Finalize && Close", command=self.finalize)
        self.finalize_btn.grid(row=0, column=1, sticky='e', padx=5) # Align right

        # --- Final Setup ---
        self.language_var.set(LANGUAGES[0]) # Set default language
        self.update_voice_dropdown() # Populate voices for default language
        self.clear_waveform() # Draw an empty plot initially

        # --- End of create_widgets ---

    def update_voice_dropdown(self):
        """Updates the voice combobox based on the selected language."""
        selected_language = self.language_var.get()
        voices = LANGUAGES_VOICES.get(selected_language, [])
        self.voice_combo['values'] = voices
        if voices:
            # Check if current voice is valid for the new language, else reset
            current_voice = self.voice_var.get()
            if current_voice not in voices:
                self.voice_var.set(voices[0]) # Set to first available voice
        else:
            self.voice_var.set('') # Clear voice if no voices for language
        print(f"Updated voice dropdown for language '{selected_language}': {voices}")

    def handle_language_change(self, event=None):
        """Handle language selection change."""
        self.update_voice_dropdown()
        # Optionally trigger voice change logic if needed, or let user select voice explicitly
        # self.handle_voice_change()

# --- Modified Handlers ---
    def handle_voice_change(self, event=None):
        """Handle voice selection changes and optionally regenerate audio"""
        if self.current_gui_selection is not None:
            details = self.reviewable_segment_details.get(self.current_gui_selection)
            if details:
                new_voice = self.voice_var.get()
                if new_voice != details['voice']:
                    details['voice'] = new_voice
                    # Update listbox display to show new voice
                    self.update_segment_display_name(self.current_gui_selection)
                    if messagebox.askyesno("Voice Changed", "Would you like to regenerate the segment with the new voice?"):
                        self.redo_segment()

    # --- New Handlers for Image/Music Changes ---
    def handle_bg_change(self, event=None):
        """Handle background image selection change."""
        print("DEBUG: handle_bg_change triggered") # DEBUG
        if self.current_gui_selection is not None:
            # DEBUG: Check selection index and details before modification
            print(f"DEBUG handle_bg_change: Modifying index {self.current_gui_selection}")
            details = self.reviewable_segment_details.get(self.current_gui_selection)
            print(f"DEBUG handle_bg_change: Details before change = {details}") # DEBUG
            if details:
                selected_name = self.bg_image_var.get()
                selected_base_path = self.name_to_path.get(selected_name)
                details['bg_image'] = selected_base_path # Store the base path
                # Get current speaker context to pass to preview update
                speaker_context = getattr(self, '_current_preview_context', 'none')
                # Call preview update with the new base path and existing context
                self._update_visual_preview(
                    bg_path=details.get('bg_image'),
                    host_base_path=details.get('host_image'), # Pass current host base path
                    guest_base_path=details.get('guest_image'), # Pass current guest base path
                    speaker_context=speaker_context
                )
                print(f"Segment {self.current_gui_selection}: Background changed to {selected_name}")
                details['bg_image'] = selected_base_path # Store the base path
                # Get current speaker context to pass to preview update
                speaker_context = getattr(self, '_current_preview_context', 'none')
                # Call preview update with the new base path and existing context
                self._update_visual_preview(
                    bg_path=details.get('bg_image'),
                    host_base_path=details.get('host_image'), # Pass current host base path
                    guest_base_path=details.get('guest_image'), # Pass current guest base path
                    speaker_context=speaker_context
                )
                print(f"Segment {self.current_gui_selection}: Background changed to {selected_name}")

    # --- Helper to find the corresponding 'closed' path ---
    def _get_corresponding_closed_path(self, current_path):
        """Given a path (potentially in 'open'), find the corresponding path in 'closed'."""
        if not current_path or current_path == NO_IMAGE or not os.path.exists(current_path):
            return current_path # Return original if None, placeholder, or invalid

        try:
            current_dir = os.path.dirname(current_path)
            current_filename = os.path.basename(current_path)

            if os.path.basename(current_dir) == 'closed':
                return current_path # Already the closed path

            if os.path.basename(current_dir) == 'open':
                parent_dir = os.path.dirname(current_dir)
                closed_dir = os.path.join(parent_dir, 'closed')
                # Find the first image in the closed dir (assuming structure consistency)
                if os.path.isdir(closed_dir):
                    image_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp')
                    closed_images = sorted([
                        os.path.join(closed_dir, f)
                        for f in os.listdir(closed_dir)
                        if os.path.isfile(os.path.join(closed_dir, f)) and f.lower().endswith(image_extensions)
                    ])
                    if closed_images:
                        print(f"DEBUG _get_corresponding_closed_path: Found closed path {os.path.basename(closed_images[0])} for open path {current_filename}")
                        return closed_images[0] # Return the full path of the first closed image
                    else:
                         print(f"DEBUG _get_corresponding_closed_path: No images found in corresponding closed dir '{closed_dir}' for {current_filename}")
                else:
                     print(f"DEBUG _get_corresponding_closed_path: Corresponding closed dir '{closed_dir}' not found for {current_filename}")

            # If not in 'open' or 'closed', or if closed counterpart not found, return original
            print(f"DEBUG _get_corresponding_closed_path: Could not determine closed path for {current_filename}. Returning original.")
            return current_path
        except Exception as e:
            print(f"DEBUG _get_corresponding_closed_path: Error processing {current_path}: {e}. Returning original.")
            return current_path

    def handle_host_img_change(self, event=None):
        """Handle host image selection change."""
        print("DEBUG: handle_host_img_change triggered") # DEBUG
        if self.current_gui_selection is not None:
            details = self.reviewable_segment_details.get(self.current_gui_selection)
            if details:
                selected_name = self.host_image_var.get()
                selected_path = self.name_to_path.get(selected_name) # Path could be open or closed

                # --- Get the corresponding CLOSED path to store ---
                closed_path_to_store = self._get_corresponding_closed_path(selected_path)
                print(f"DEBUG handle_host_img_change: Selected path='{selected_path}', Closed path to store='{closed_path_to_store}'")

                details['host_image'] = closed_path_to_store # Store the 'closed' path as the base

                # Get current speaker context to pass to preview update
                speaker_context = getattr(self, '_current_preview_context', 'none')
                # Call preview update with the STORED BASE (closed) path
                self._update_visual_preview(
                    bg_path=details.get('bg_image'),
                    host_base_path=details.get('host_image'), # Pass the newly stored closed path
                    guest_base_path=details.get('guest_image'),
                    speaker_context=speaker_context
                )
                print(f"Segment {self.current_gui_selection}: Host image changed to {selected_name} (Stored base: {os.path.basename(closed_path_to_store)})")


    def handle_guest_img_change(self, event=None):
        """Handle guest image selection change."""
        print("DEBUG: handle_guest_img_change triggered") # DEBUG
        if self.current_gui_selection is not None:
            details = self.reviewable_segment_details.get(self.current_gui_selection)
            if details:
                selected_name = self.guest_image_var.get()
                selected_path = self.name_to_path.get(selected_name) # Path could be open or closed

                # --- Get the corresponding CLOSED path to store ---
                closed_path_to_store = self._get_corresponding_closed_path(selected_path)
                print(f"DEBUG handle_guest_img_change: Selected path='{selected_path}', Closed path to store='{closed_path_to_store}'")

                details['guest_image'] = closed_path_to_store # Store the 'closed' path as the base

                # Get current speaker context to pass to preview update
                speaker_context = getattr(self, '_current_preview_context', 'none')
                # Call preview update with the STORED BASE (closed) path
                self._update_visual_preview(
                    bg_path=details.get('bg_image'),
                    host_base_path=details.get('host_image'),
                    guest_base_path=details.get('guest_image'), # Pass the newly stored closed path
                    speaker_context=speaker_context
                )
                print(f"Segment {self.current_gui_selection}: Guest image changed to {selected_name} (Stored base: {os.path.basename(closed_path_to_store)})")

    def handle_intro_music_change(self, event=None):
        """Handle intro music selection change."""
        print("DEBUG: handle_intro_music_change triggered") # DEBUG
        if self.current_gui_selection is not None:
            # DEBUG: Check selection index and details before modification
            print(f"DEBUG handle_intro_music_change: Modifying index {self.current_gui_selection}")
            details = self.reviewable_segment_details.get(self.current_gui_selection)
            print(f"DEBUG handle_intro_music_change: Details before change = {details}") # DEBUG
            if details:
                selected_name = self.intro_music_var.get()
                selected_path = self.name_to_path.get(selected_name)
                details['intro_music'] = selected_path
                print(f"Segment {self.current_gui_selection}: Intro music changed to {selected_name}")
                # No regeneration needed unless user clicks Redo

    def handle_outro_music_change(self, event=None):
        """Handle outro music selection change."""
        print("DEBUG: handle_outro_music_change triggered") # DEBUG
        if self.current_gui_selection is not None:
            # DEBUG: Check selection index and details before modification
            print(f"DEBUG handle_outro_music_change: Modifying index {self.current_gui_selection}")
            details = self.reviewable_segment_details.get(self.current_gui_selection)
            print(f"DEBUG handle_outro_music_change: Details before change = {details}") # DEBUG
            # Only process if the currently selected segment IS the outro segment
            if details and details.get('type') == 'outro':
                selected_name = self.outro_music_var.get()
                selected_path = self.name_to_path.get(selected_name)
                details['outro_music'] = selected_path
                details['audio_path'] = selected_path # Update the path to load
                print(f"Segment {self.current_gui_selection} (Outro): Music changed to {selected_name}")
                # Reload player and waveform with the new music
                if selected_path and selected_path != NO_MUSIC and os.path.exists(selected_path):
                    if self.player.load_file(selected_path):
                        self.update_waveform(selected_path)
                    else:
                        messagebox.showerror("Load Error", f"Failed to load selected outro music:\n{selected_path}")
                        self.clear_waveform()
                else:
                    self.player.load_file(None) # Clear player if "None" selected
                    self.clear_waveform()

    # --- New Handlers for Processing Options ---
    def handle_ffmpeg_change(self):
        """Update stored FFmpeg setting when Checkbutton is toggled."""
        if self.current_gui_selection is not None:
            details = self.reviewable_segment_details.get(self.current_gui_selection)
            if details and details.get('type') == 'speech':
                new_state = self.ffmpeg_enhancement_var.get()
                details['apply_ffmpeg_enhancement'] = new_state
                deesser_enabled = self.deesser_var.get() if new_state else False
                details['apply_deesser'] = deesser_enabled
                print(f"Segment {self.current_gui_selection}: FFmpeg Enhancement set to {new_state}")
                print(f"Segment {self.current_gui_selection}: De-esser set to {deesser_enabled}")
                
                # Update de-esser frequency Spinbox state
                self.deesser_freq_spinbox.configure(state='normal' if (new_state and deesser_enabled) else 'disabled')
                
                self._toggle_ffmpeg_params_visibility() # Show/hide parameter controls
                # Optionally ask to regenerate here? For now, rely on Redo button.

    def handle_deesser_change(self):
        """Handle changes to the de-esser checkbox."""
        if self.current_gui_selection is not None:
            details = self.reviewable_segment_details.get(self.current_gui_selection)
            if details and details.get('type') == 'speech':
                deesser_enabled = self.deesser_var.get()
                details['apply_deesser'] = deesser_enabled
                # Update spinbox state based on both FFmpeg and de-esser state
                ffmpeg_enabled = self.ffmpeg_enhancement_var.get()
                self.deesser_freq_spinbox.configure(state='normal' if (ffmpeg_enabled and deesser_enabled) else 'disabled')
                print(f"Segment {self.current_gui_selection}: De-esser set to {deesser_enabled}")

    def _toggle_ffmpeg_params_visibility(self):
        """Shows or hides the FFmpeg parameter controls based on the main checkbox."""
        try:
            if self.ffmpeg_enhancement_var.get():
                # Check if already gridded using grid_info(), if not, grid it
                if not self.ffmpeg_params_frame.grid_info():
                    self.ffmpeg_params_frame.grid(**self.ffmpeg_params_frame_grid_config)
            else:
                # Check if gridded before trying to forget
                if self.ffmpeg_params_frame.grid_info():
                    self.ffmpeg_params_frame.grid_forget()
        except tk.TclError as e:
             print(f"Warning: TclError toggling FFmpeg params visibility (widget might not exist yet): {e}")

    def handle_trim_change(self):
        """Update stored trim value when Spinbox command is triggered (arrow keys/direct click)."""
        # This handles the command triggered by Spinbox interaction, but not direct text entry.
        # We use trace_add for direct text entry validation/update.
        if self.current_gui_selection is not None:
            details = self.reviewable_segment_details.get(self.current_gui_selection)
            if details and details.get('type') == 'speech':
                try:
                    new_trim = self.trim_end_ms_var.get() # Get value directly from Int Var
                    if new_trim >= 0: # Basic validation
                       details['trim_end_ms'] = new_trim
                       print(f"Segment {self.current_gui_selection}: Trim End set to {new_trim}ms")
                    else:
                       print(f"Segment {self.current_gui_selection}: Invalid trim value entered ({new_trim}). Ignoring.")
                       # Optionally reset the var/widget to the last valid value stored in details
                       self.trim_end_ms_var.set(details.get('trim_end_ms', 120))
                except tk.TclError:
                    print(f"Segment {self.current_gui_selection}: Invalid trim value entered. Ignoring.")
                    # Reset var/widget if invalid input
                    self.trim_end_ms_var.set(details.get('trim_end_ms', 120))

    def handle_trim_change_trace(self, *args):
        """Update stored trim value when the trim_end_ms_var changes (e.g., direct text input)."""
        # This trace handles changes to the variable itself, including direct typing.
        if self.current_gui_selection is not None:
            details = self.reviewable_segment_details.get(self.current_gui_selection)

    def handle_padding_change(self):
        """Update stored padding value when Spinbox command is triggered (arrow keys/direct click)."""
        if self.current_gui_selection is not None:
            details = self.reviewable_segment_details.get(self.current_gui_selection)
            if details and details.get('type') == 'speech':
                try:
                    new_padding = self.padding_ms_var.get() # Get value directly from Int Var
                    if new_padding >= 0: # Basic validation
                       details['padding_ms'] = new_padding
                       print(f"Segment {self.current_gui_selection}: Padding set to {new_padding}ms")
                    else:
                       print(f"Segment {self.current_gui_selection}: Invalid padding value entered ({new_padding}). Ignoring.")
                       # Optionally reset the var/widget to the last valid value stored in details
                       self.padding_ms_var.set(details.get('padding_ms', 0))
                except tk.TclError:
                    print(f"Segment {self.current_gui_selection}: Invalid padding value entered. Ignoring.")
                    # Reset var/widget if invalid input
                    self.padding_ms_var.set(details.get('padding_ms', 0))

    def handle_padding_change_trace(self, *args):
        """Update stored padding value when the padding_ms_var changes (e.g., direct text input)."""
        if self.current_gui_selection is not None:
            details = self.reviewable_segment_details.get(self.current_gui_selection)
            if details and details.get('type') == 'speech':
                try:
                    new_padding = self.padding_ms_var.get()
                    if new_padding >= 0:
                       # Check if the value actually changed to avoid redundant updates
                       if details.get('padding_ms') != new_padding:
                           details['padding_ms'] = new_padding
                           print(f"Segment {self.current_gui_selection} (Trace): Padding set to {new_padding}ms")
                    # No else needed here, as invalid input might trigger TclError caught below
                except tk.TclError:
                    # This can happen if the user types non-integer characters temporarily
                    # We don't necessarily need to reset immediately, wait for valid input or focus out.
                    # print(f"Segment {self.current_gui_selection} (Trace): Invalid intermediate padding value.")
                    pass # Allow temporary invalid states during typing

            if details and details.get('type') == 'speech':
                try:
                    new_trim = self.trim_end_ms_var.get()
                    if new_trim >= 0:
                       # Check if the value actually changed to avoid redundant updates
                       if details.get('trim_end_ms') != new_trim:
                           details['trim_end_ms'] = new_trim
                           print(f"Segment {self.current_gui_selection} (Trace): Trim End set to {new_trim}ms")
                    # No else needed here, as invalid input might trigger TclError caught below
                except tk.TclError:
                    # This can happen if the user types non-integer characters temporarily
                    # We don't necessarily need to reset immediately, wait for valid input or focus out.
                    # print(f"Segment {self.current_gui_selection} (Trace): Invalid intermediate trim value.")
                    pass # Allow temporary invalid states during typing

    # --- Handlers for individual FFmpeg parameters ---
    def handle_ffmpeg_param_change(self):
        """Generic handler for Spinbox command changes for FFmpeg params."""
        # This handles arrow keys/direct clicks on Spinboxes
        self._update_ffmpeg_details_from_vars()

    def handle_ffmpeg_param_change_trace(self, *args):
        """Generic handler for variable traces for FFmpeg params."""
        # This handles direct text input or programmatic changes
        self._update_ffmpeg_details_from_vars()

    def _update_ffmpeg_details_from_vars(self):
        """Reads FFmpeg parameter variables and updates the details dictionary."""
        if self.current_gui_selection is None: return
        details = self.reviewable_segment_details.get(self.current_gui_selection)
        if not details or details.get('type') != 'speech': return

        updated = False
        try:
            # Noise Reduction
            nr_level = self.nr_level_var.get()
            if nr_level >= 0 and nr_level <= 97 and details.get('nr_level') != nr_level:
                details['nr_level'] = nr_level
                print(f"Segment {self.current_gui_selection}: NR Level set to {nr_level}")
                updated = True

            # Compressor Threshold
            try: # Validate float entry
                comp_thresh = self.compress_thresh_var.get() # Get directly from DoubleVar
                if comp_thresh >= 0.001 and comp_thresh <= 1.0 and details.get('compress_thresh') != comp_thresh:
                     details['compress_thresh'] = comp_thresh
                     print(f"Segment {self.current_gui_selection}: Comp Threshold set to {comp_thresh:.3f}")
                     updated = True
                elif comp_thresh < 0.001 or comp_thresh > 1.0:
                     print(f"Segment {self.current_gui_selection}: Invalid Comp Threshold ({comp_thresh:.3f}). Clamping or reverting might be needed.")
                     # Optionally clamp or reset the variable here if desired
            except tk.TclError:
                print(f"Segment {self.current_gui_selection}: Invalid Comp Threshold input.")
                # Optionally reset variable to last known good value from details

            # Compressor Ratio
            comp_ratio = self.compress_ratio_var.get()
            if comp_ratio >= 1 and comp_ratio <= 20 and details.get('compress_ratio') != comp_ratio:
                details['compress_ratio'] = comp_ratio
                print(f"Segment {self.current_gui_selection}: Comp Ratio set to {comp_ratio}")
                updated = True

            # Norm Frame Length
            norm_f = self.norm_frame_len_var.get()
            if norm_f >= 10 and norm_f <= 8000 and details.get('norm_frame_len') != norm_f:
                details['norm_frame_len'] = norm_f
                print(f"Segment {self.current_gui_selection}: Norm Frame set to {norm_f}")
                updated = True

            # Norm Gauss Size (ensure odd)
            norm_g = self.norm_gauss_size_var.get()
            if norm_g >= 3 and norm_g <= 301:
                if norm_g % 2 == 0: # If even, adjust to nearest lower odd number
                    norm_g -= 1
                    self.norm_gauss_size_var.set(norm_g) # Update the variable/spinbox too
                if details.get('norm_gauss_size') != norm_g:
                    details['norm_gauss_size'] = norm_g
                    print(f"Segment {self.current_gui_selection}: Norm Gauss set to {norm_g}")
                    updated = True
            elif norm_g < 3: # Handle lower bound if needed
                 self.norm_gauss_size_var.set(3) # Set to minimum odd
                 if details.get('norm_gauss_size') != 3:
                    details['norm_gauss_size'] = 3
                    print(f"Segment {self.current_gui_selection}: Norm Gauss set to {3}")
                    updated = True


        except tk.TclError:
            # This can happen with invalid intermediate input in Spinboxes/Entries
            # print(f"Segment {self.current_gui_selection} (FFmpeg Trace): Invalid intermediate value.")
            pass # Allow temporary invalid states during typing

        # if updated:
            # Optionally ask to regenerate here, or rely on Redo button
            # print("FFmpeg parameters updated in details.")

    def add_special_segment(self, segment_type):
        """Adds an Intro or Outro segment to the GUI."""
        if segment_type not in ['intro', 'outro']:
            return

        gui_index = self.segment_listbox.size()
        display_name = "Intro" if segment_type == 'intro' else "Outro"
        default_music_list = self.intro_music_files if segment_type == 'intro' else self.outro_music_files
        default_music = default_music_list[0] if default_music_list else NO_MUSIC

        # --- Set Default Visuals ---
        default_bg = self.background_files[0] if self.background_files else NO_IMAGE
        default_host = self.host_closed_image_files[0] if self.host_closed_image_files else NO_IMAGE
        default_guest = self.guest_closed_image_files[0] if self.guest_closed_image_files else NO_IMAGE

        details = {
            'type': segment_type,
            'text': f"[{display_name} Music]", # Placeholder text
            'voice': None, # No voice
            'apply_deesser': True, # Default de-esser state
            'original_index': -1, # No corresponding index in original all_segment_files
            'gain': 1.0, # Not applicable
            'bg_image': default_bg,
            'host_image': default_host,
            'guest_image': default_guest,
            'intro_music': default_music if segment_type == 'intro' else NO_MUSIC,
            'outro_music': default_music if segment_type == 'outro' else NO_MUSIC,
            'audio_path': default_music # Store the actual music path here for loading
        }
        self.reviewable_segment_details[gui_index] = details
        # No mapping needed for gui_index_to_original_index for these special types

        # Add to listbox
        self.segment_listbox.insert(tk.END, f"--- {display_name} ---") # Use insert END
        print(f"TTSDevGUI: Added special segment: {display_name} (GUI Index {gui_index})")



    def add_reviewable_segment(self, original_index, file_path, text, voice, padding_ms=0): # Added padding_ms
        """Adds a speech segment to the GUI for review, setting default visuals/music."""
        gui_index = self.segment_listbox.size()
        # Load default gain from voice config instead of hardcoding
        voice_config = load_voice_config(voice)
        default_gain = voice_config.get('gain_factor', 1.0) # Get gain from config, default 1.0

        # --- Helper to find the default CLOSED image path ---
        def get_default_closed_image(character_type):
            closed_dir = os.path.join(IMAGE_DIR, character_type, "closed")
            print(f"DEBUG get_default_closed_image ({character_type}): Searching in '{closed_dir}'") # DEBUG
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
                print(f"DEBUG get_default_closed_image ({character_type}): Found potential closed images: {[os.path.basename(p) for p in closed_images]}") # DEBUG
                if closed_images:
                    print(f"DEBUG get_default_closed_image ({character_type}): Using first found: {os.path.basename(closed_images[0])}") # DEBUG
                    return closed_images[0] # Return the full path of the first found closed image
                else:
                    print(f"DEBUG get_default_closed_image ({character_type}): No images found in {closed_dir}")
                    return NO_IMAGE
            except Exception as e:
                print(f"DEBUG get_default_closed_image ({character_type}): Error listing dir {closed_dir}: {e}")
                return NO_IMAGE

        # --- Set Default Visuals and Music ---
        default_bg = self.background_files[0] if self.background_files else NO_IMAGE
        default_host_closed = get_default_closed_image("host")   # Explicitly get default closed path
        default_guest_closed = get_default_closed_image("guest") # Explicitly get default closed path
        default_intro = next((f for f in self.intro_music_files if f != NO_MUSIC), NO_MUSIC)
        default_outro = next((f for f in self.outro_music_files if f != NO_MUSIC), NO_MUSIC)

        print(f"DEBUG add_reviewable_segment (GUI Index {gui_index}): Default Host Closed Path: {default_host_closed}") # DEBUG
        print(f"DEBUG add_reviewable_segment (GUI Index {gui_index}): Default Guest Closed Path: {default_guest_closed}") # DEBUG

        self.reviewable_segment_details[gui_index] = {
            'type': 'speech',
            'text': text,
            'voice': voice,
            'original_index': original_index,
            'gain': default_gain,
            'bg_image': default_bg,
            'host_image': default_host_closed,   # Store the specific closed path as the base
            'guest_image': default_guest_closed, # Store the specific closed path as the base
            'intro_music': default_intro,
            'outro_music': default_outro,
            'audio_path': file_path,
            'padding_ms': padding_ms,
            # NOTE: Default processing parameters are NOT stored here anymore.
            # The 'on_segment_select' method applies voice-specific defaults
            # when the segment is first loaded into the UI.
            # If the user modifies settings via the GUI, those specific values
            # (e.g., 'apply_ffmpeg_enhancement', 'nr_level') will be saved
            # into this 'details' dictionary for *this segment only* by the
            # respective handler functions (handle_ffmpeg_change, _update_ffmpeg_details_from_vars, etc.).
        }
        self.gui_index_to_original_index[gui_index] = original_index
        self.update_segment_display_name(gui_index, file_path) # Add initial entry with duration
        print(f"TTSDevGUI: Added reviewable segment: GUI Index {gui_index}, Original Index {original_index}, File: {file_path}")

    def update_segment_display_name(self, gui_index, file_path=None):
        """Updates the text displayed in the listbox for a given GUI index."""
        details = self.reviewable_segment_details.get(gui_index)
        if not details: return

        original_index = details['original_index']
        if file_path is None: # If file path not provided, get it from the main list
            if original_index < len(self.all_segment_files):
                file_path = self.all_segment_files[original_index]
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
        if gui_index < self.segment_listbox.size():
            self.segment_listbox.delete(gui_index)
            self.segment_listbox.insert(gui_index, name)
        elif gui_index == self.segment_listbox.size():
            self.segment_listbox.insert(tk.END, name) # Should happen during add_reviewable_segment
        # Removed stray 'if selection:' block
            print(f"TTSDevGUI: Selected listbox index {self.current_gui_selection}") # Debug print

            details = self.reviewable_segment_details.get(self.current_gui_selection)
            original_index = self.gui_index_to_original_index.get(self.current_gui_selection)

            # --- Reset UI elements ---
            self.text_display.delete(1.0, tk.END)
            self.voice_var.set("")
            self.bg_image_var.set("")
            self.host_image_var.set("")
            self.guest_image_var.set("")
            self.intro_music_var.set("")
            self.outro_music_var.set("")
            self.gain_var.set(1.0)
            self.player.load_file(None) # Clear player first
            self.clear_waveform()
            self._update_visual_preview() # Clear preview
            if self.player: self.player.redo_btn.configure(state=tk.DISABLED) # Use player's button
            if self.gain_frame.winfo_ismapped(): self.gain_frame.pack_forget() # Hide gain initially

            # --- Populate UI with selected segment data ---
            if details:  # Removed additional conditions since we have the details
                # 1. Populate Text and Voice
                text_content = details.get('text', '')
                self.text_display.delete(1.0, tk.END)  # Clear again to be safe
                self.text_display.insert(tk.END, text_content)
                print(f"DEBUG: Inserted text content: {text_content[:50]}...")  # Debug print
                self.voice_var.set(details['voice'])

                # 2. Populate Image/Music Selections (using BASENAMES for Comboboxes)
                # Get the stored full paths first
                bg_path = details.get('bg_image', NO_IMAGE)
                host_path = details.get('host_image', NO_IMAGE)
                guest_path = details.get('guest_image', NO_IMAGE)
                intro_path = details.get('intro_music', NO_MUSIC)
                outro_path = details.get('outro_music', NO_MUSIC)

                # Set the StringVars using the corresponding basenames or None values
                self.bg_image_var.set(os.path.basename(bg_path) if bg_path != NO_IMAGE else NO_IMAGE)
                self.host_image_var.set(os.path.basename(host_path) if host_path != NO_IMAGE else NO_IMAGE)
                self.guest_image_var.set(os.path.basename(guest_path) if guest_path != NO_IMAGE else NO_IMAGE)
                self.intro_music_var.set(os.path.basename(intro_path) if intro_path != NO_MUSIC else NO_MUSIC)
                self.outro_music_var.set(os.path.basename(outro_path) if outro_path != NO_MUSIC else NO_MUSIC)


                # 3. Update Visual Preview
                self._update_visual_preview(bg_path=bg_path, host_path=host_path, guest_path=guest_path)

                # 4. Load Audio File
                file_path = self.all_segment_files[original_index]
                print(f"TTSDevGUI: Loading file for original index {original_index}: {file_path}") # Debug print
                if self.player.load_file(file_path):
                     self.redo_btn.configure(state=tk.NORMAL) # Enable redo button only if load succeeds
                     self.update_waveform(file_path) # Update waveform on successful load
                else:
                     # Loading failed, show error
                     messagebox.showerror("Load Error", f"Failed to load audio for selected segment:\n{file_path}")
                     # Keep redo disabled, waveform/preview already cleared

                # 5. Set and display gain control
                self.gain_var.set(details.get('gain', 1.0)) # Set scale to stored value
                self._update_gain_label_format() # Update label format
                # Removed incorrect pack call: self.gain_frame.pack(fill=tk.X, pady=5, before=self.shortcuts_label)
                # The grid calls in on_segment_select (lines ~520, ~671) handle placing this frame.

            else:
                 # Error case: Could not find details or original index
                 print(f"TTSDevGUI: Error - Could not find details or original index for GUI index {self.current_gui_selection}")
                 # UI elements are already cleared from the start of the 'if selection:' block



    def _update_gain_label_format(self, *args):
        """Formats the gain value label to two decimal places."""
        try:
            value = self.gain_var.get()
            self.gain_value_label.config(text=f"{value:.2f}")
        except Exception:
            self.gain_value_label.config(text="-.--") # Handle potential errors

    def clear_waveform(self):
        """Clears the waveform plot and removes the player's progress line."""
        # Remove the progress line from the player if it exists
        if hasattr(self, 'player') and self.player and self.player.progress_line and self.player.progress_line in self.ax.lines:
            try:
                self.player.progress_line.remove()
                self.player.progress_line = None
            except Exception as e:
                print(f"TTSDevGUI: Error removing progress line: {e}")

        # Clear the matplotlib axes
        self.ax.clear()
        self.ax.set_title("No Segment Selected")
        self.ax.set_xlabel("Time (s)")
        self.ax.set_ylabel("Amplitude")
        self.ax.set_yticks([]) # Hide y-axis ticks when empty
        self.ax.set_xticks([]) # Hide x-axis ticks when empty
        try:
            self.waveform_canvas_agg.draw_idle() # Use draw_idle() for safer redrawing
        except Exception as e:
            print(f"TTSDevGUI: Error clearing waveform canvas: {e}")

    def update_waveform(self, file_path):
        """Reads an audio file and plots its waveform."""
        self.ax.clear()
        if not file_path or not os.path.exists(file_path):
            print(f"TTSDevGUI: Waveform - File not found or invalid: {file_path}")
            self.clear_waveform()
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

                self.ax.plot(time, data, linewidth=0.5) # Thinner line for detail
                self.ax.set_title(f"{os.path.basename(file_path)} ({duration:.2f}s)")
                self.ax.set_xlabel("Time (s)")
                self.ax.set_ylabel("Amplitude")
                # Set reasonable default y-limits, can be adjusted if needed
                max_abs_val = np.max(np.abs(data)) if len(data) > 0 else 1.0
                self.ax.set_ylim(-max_abs_val * 1.1, max_abs_val * 1.1)
                self.ax.grid(True) # Add grid
                self.fig.tight_layout() # Adjust layout after plotting
                self.waveform_canvas_agg.draw_idle() # Use draw_idle() for safer redrawing
        except Exception as e:
            print(f"TTSDevGUI: Error reading/plotting waveform: {e}") # Removed file_path from here
            messagebox.showerror("Waveform Error", f"Could not display waveform.\\n\\nError: {e}")
            self.clear_waveform() # Clear plot on error

    def on_waveform_click(self, event):
        """Handle clicks on the waveform plot for seeking."""
        # Ignore clicks outside the axes, or if player/file/duration invalid
        if event.inaxes != self.ax or not self.player or not self.player.current_file or not hasattr(self.player, 'duration'):
            return

        # event.xdata gives the clicked time coordinate
        clicked_time = event.xdata
        if clicked_time is not None and clicked_time >= 0 and clicked_time <= self.player.duration:
            print(f"TTSDevGUI: Waveform clicked at time {clicked_time:.2f}s")
            # Call the player's seek method
            self.player.seek_to_time(clicked_time)
        else:
             print(f"TTSDevGUI: Waveform click ignored (time={clicked_time})")
# End of on_waveform_click. Removed incorrect plotting try/except block.

    def handle_gain_change(self, value_str): # Scale passes value as string
        """Update the stored gain value when the scale is moved for any selected segment."""
        if self.current_gui_selection is not None:
            details = self.reviewable_segment_details.get(self.current_gui_selection)
            if details: # Check if details exist for the selected segment
                try:
                    new_gain = float(value_str)
                    details['gain'] = new_gain
                    # No need to regenerate automatically, user clicks Redo
                    # print(f"TTSDevGUI: Updated stored gain for segment {self.current_gui_selection} to {new_gain:.2f}")
                except ValueError:
                    print("TTSDevGUI: Invalid gain value from scale.")

    def redo_segment(self):
        if self.current_gui_selection is None or self.temp_dir is None:
             messagebox.showwarning("Cannot Redo", "Please select a segment from the list first.")
             return

        details = self.reviewable_segment_details.get(self.current_gui_selection)
        original_index = self.gui_index_to_original_index.get(self.current_gui_selection)

        if not details or original_index is None:
             messagebox.showerror("Error", f"Could not find details for selected segment.")
             return

        if original_index >= len(self.all_segment_files):
             messagebox.showerror("Error", f"Internal error: Original index out of bounds.")
             return

        old_file_path = self.all_segment_files[original_index]
        # Get the current text from the text display
        text = self.text_display.get(1.0, tk.END).strip()

        if not text:
            messagebox.showerror("Error", "Text cannot be empty.")
            return

        # Update the stored text and get current voice
        details['text'] = text
        voice = self.voice_var.get() # Use current selection from combobox
        details['voice'] = voice # Update stored voice as well

        gain_to_apply = details.get('gain', 1.0)
        padding_to_apply = details.get('padding_ms', 0)
        # Get FFmpeg processing flag and specific parameters
        apply_ffmpeg = details.get('apply_ffmpeg_enhancement', True)
        nr_level = details.get('nr_level', 35)
        compress_thresh = details.get('compress_thresh', 0.03)
        compress_ratio = details.get('compress_ratio', 2)
        norm_frame_len = details.get('norm_frame_len', 20)
        norm_gauss_size = details.get('norm_gauss_size', 15)

        # Get de-esser settings for logging
        apply_deesser = details.get('apply_deesser', True)
        deesser_freq = details.get('deesser_freq', 5000)
        
        print(f"TTSDevGUI: Redoing segment (Original Index {original_index}, GUI Index {self.current_gui_selection}, Voice: {voice}, Gain: {gain_to_apply:.2f}, Padding: {padding_to_apply}ms)")
        if apply_ffmpeg:
            print(f"  -> FFmpeg Params: NR={nr_level}, CompThresh={compress_thresh:.3f}, CompRatio={compress_ratio}, NormFrame={norm_frame_len}, NormGauss={norm_gauss_size}")
            if apply_deesser:
                print(f"  -> De-esser: Enabled (Freq: {deesser_freq} Hz)")
            else:
                print("  -> De-esser: Disabled")
        else:
            print("  -> FFmpeg Enhancement: Disabled (including De-esser)")
        print(f"  -> Old File: {old_file_path}")

        # Ensure player stops using the old file
        self.player.stop()

        # Show progress
        self.progress_bar.grid(**self.progress_bar_grid_config) # Use grid config
        self.progress_bar.start(10)
        if self.player: self.player.redo_btn.configure(state=tk.DISABLED) # Use player's button
        self.root.config(cursor="watch") # Use "watch" for broader compatibility
        self.root.update_idletasks() # Force UI update before starting thread

        # Run generation in a separate thread, passing all relevant parameters
        thread = threading.Thread(target=self._thread_generate_audio,
                                   args=(text, voice, original_index, old_file_path, gain_to_apply, padding_to_apply,
                                         apply_ffmpeg, nr_level, compress_thresh, compress_ratio, norm_frame_len, norm_gauss_size),
                                  daemon=True)
        thread.start()

    def _thread_generate_audio(self, text, voice, original_index, old_file_path, gain_factor, padding_ms,
                                apply_ffmpeg, nr_level, compress_thresh, compress_ratio, norm_frame_len, norm_gauss_size):
        """Runs audio generation in a background thread with FFmpeg parameters."""
        # Get current settings for de-esser before starting thread
        details = self.reviewable_segment_details.get(self.current_gui_selection, {})
        apply_deesser = details.get('apply_deesser', True)
        deesser_freq = details.get('deesser_freq', 5000)
        
        new_file_path, new_sr = generate_audio_segment(
            text, voice, self.speed, self.api_host, self.api_port, self.temp_dir,
            gain_factor=gain_factor,
            pad_end_ms=padding_ms,
            # Pass FFmpeg parameters
            apply_ffmpeg_enhancement=apply_ffmpeg,
            apply_deesser=apply_deesser,
            deesser_freq=deesser_freq,
            nr_level=nr_level,
            compress_thresh=compress_thresh,
            compress_ratio=compress_ratio,
            norm_frame_len=norm_frame_len,
            norm_gauss_size=norm_gauss_size
        )
# Removed plt.close(self.fig) from background thread
        # Schedule UI updates back on the main thread
        self.root.after(0, self._finish_redo_ui, new_file_path, original_index, old_file_path)

    def _finish_redo_ui(self, new_file_path, original_index, old_file_path):
        """Updates the UI after audio generation thread finishes."""
        # Stop progress indication and reset cursor
        self.progress_bar.stop()
        if self.progress_bar.grid_info(): # Check if gridded before forgetting
            self.progress_bar.grid_forget()
        self.root.config(cursor="")
        if self.player: self.player.redo_btn.configure(state=tk.NORMAL) # Re-enable player's button

        if new_file_path:
            print(f"TTSDevGUI: Segment regenerated successfully: {new_file_path}")
            # Update the file path in the main list
            self.all_segment_files[original_index] = new_file_path
            # --- BEGIN ADDED CODE ---
            # Update the audio path in the details dictionary for the current selection
            current_details = self.reviewable_segment_details.get(self.current_gui_selection)
            if current_details:
                current_details['audio_path'] = new_file_path
                print(f"TTSDevGUI: Updated reviewable_segment_details[{self.current_gui_selection}]['audio_path'] to {new_file_path}")
            else:
                print(f"TTSDevGUI: Warning - Could not find details for GUI index {self.current_gui_selection} to update audio_path.")
            # --- END ADDED CODE ---

            # Update the listbox display name
            self.update_segment_display_name(self.current_gui_selection, new_file_path)
            # plt.close(self.fig) # Close plot figure - Moved this down

            # Remove old file
            try:
                if old_file_path and os.path.exists(old_file_path) and old_file_path != new_file_path:
                    os.remove(old_file_path)
                    print(f"TTSDevGUI: Removed old file: {old_file_path}") # Corrected indentation
            except Exception as e:
                print(f"TTSDevGUI: Warning - Failed to remove old file {old_file_path}: {e}")

            # Reload the new audio file in the player and update waveform
            if not self.player.load_file(new_file_path):
                 messagebox.showerror("Load Error", f"Segment regenerated, but failed to load new audio:\n{new_file_path}")
                 self.clear_waveform()
            else:
                 # Only show success message and update waveform if loading succeeds
                 messagebox.showinfo("Success", "Segment regenerated and loaded.")
                 self.update_waveform(new_file_path)
                 # Consider closing the figure *after* successful update? Or maybe it's fine here.
                 # Let's keep plt.close where it was for now, as waveform update clears/redraws axes.
            plt.close(self.fig) # Close plot figure
        else:
            messagebox.showerror("Error", "Failed to regenerate speech segment. Check console output. Keeping original segment.")
            # Keep the old file in the player if processing failed? Reload old one.
            if old_file_path and os.path.exists(old_file_path):
                if not self.player.load_file(old_file_path): # Attempt to reload old file
                    print(f"TTSDevGUI: Failed to reload original file {old_file_path} after redo failure.")
                    self.clear_waveform()
                else:
                    self.update_waveform(old_file_path) # Update waveform for old file
            else:
                self.player.load_file(None) # Clear player if old file doesn't exist
                self.clear_waveform()
            # Removed redundant clear_waveform and load_file calls here

    def finalize(self):
        """Signal that we're done reviewing. Returns structured segment details."""
        print("TTSDevGUI: Finalize clicked.")
        if self.player:
            self.player.cleanup()

        # Prepare the final structured list based on the order in the listbox
        self.final_structured_details = []
        for i in range(self.segment_listbox.size()):
            original_details = self.reviewable_segment_details.get(i)
            if original_details:
                # Create a copy to modify for the final output JSON
                details = original_details.copy()

                # Ensure type exists for all segments
                segment_type = details.get('type', 'speech')
                details['type'] = segment_type

                # --- Determine Context-Specific Image Paths for Final JSON ---
                voice = details.get('voice')
                host_base_path = details.get('host_image')   # Path to 'closed' image or NO_IMAGE
                guest_base_path = details.get('guest_image') # Path to 'closed' image or NO_IMAGE

                host_path_to_use = host_base_path
                guest_path_to_use = guest_base_path
                speaker_context = 'none' # Default

                if segment_type == 'speech':
                    if voice == self.host_voice:
                        speaker_context = 'host_speaking'
                    elif voice == self.guest_voice:
                        speaker_context = 'guest_speaking'
                elif segment_type in ['intro', 'outro']:
                    speaker_context = 'intro_outro'

                print(f"  Finalizing Segment {i+1} ({segment_type}, Voice: {voice}, Context: {speaker_context})")

                # --- Helper Function to Find Corresponding Open Image (Copied from _update_visual_preview) ---
                # Note: Could be refactored into a class method if used more widely
                def find_corresponding_open_image(base_path):
                    print(f"DEBUG (finalize) find_corresponding_open_image: Called with base_path='{base_path}'")
                    if not base_path or base_path == NO_IMAGE:
                        print("DEBUG (finalize) find_corresponding_open_image: base_path is None or NO_IMAGE, returning base_path.")
                        return base_path
                    if not os.path.exists(base_path):
                         print(f"DEBUG (finalize) find_corresponding_open_image: base_path '{base_path}' does not exist, returning base_path.")
                         return base_path

                    try:
                        closed_dir = os.path.dirname(base_path)
                        closed_filename = os.path.basename(base_path)
                        parent_dir = os.path.dirname(closed_dir)
                        open_dir = os.path.join(parent_dir, 'open')
                        print(f"DEBUG (finalize) find_corresponding_open_image: Checking for open_dir='{open_dir}'")
                        if not os.path.isdir(open_dir):
                            print(f"    -> (finalize) Corresponding 'open' directory not found: {open_dir}. Returning closed path.")
                            return base_path

                        print(f"DEBUG (finalize) find_corresponding_open_image: Listing contents of open_dir='{open_dir}'") # ADDED LOGGING
                        try:
                            dir_contents = os.listdir(open_dir)
                            print(f"DEBUG (finalize) find_corresponding_open_image: Directory contents: {dir_contents}") # ADDED LOGGING
                        except Exception as listdir_e:
                            print(f"DEBUG (finalize) find_corresponding_open_image: Error listing directory '{open_dir}': {listdir_e}") # ADDED LOGGING
                            return base_path # Fallback on error

                        # Find image files in the 'open' directory. Use the first one found if only one exists.
                        image_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp')

                        closed_stem = os.path.splitext(closed_filename)[0] # Get filename without extension
                        print(f"DEBUG (finalize) find_corresponding_open_image: closed_dir='{closed_dir}', closed_stem='{closed_stem}'")

                        if os.path.basename(closed_dir) != 'closed':
                            print(f"DEBUG (finalize) find_corresponding_open_image: Base path '{closed_filename}' not in 'closed' dir, returning base_path.")
                            return base_path
                        parent_dir = os.path.dirname(closed_dir)
                        open_dir = os.path.join(parent_dir, 'open')
                        print(f"DEBUG (finalize) find_corresponding_open_image: Checking for open_dir='{open_dir}'")
                        if not os.path.isdir(open_dir):
                            print(f"    -> (finalize) Corresponding 'open' directory not found: {open_dir}. Returning closed path.")
                            return base_path

                        # Find image files in the 'open' directory. Use the first one found if only one exists.
                        image_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp')
                        all_open_images = []
                        for f in os.listdir(open_dir):
                            if os.path.isfile(os.path.join(open_dir, f)) and f.lower().endswith(image_extensions):
                                all_open_images.append(f)

                        print(f"DEBUG (finalize) find_corresponding_open_image: Found open images in '{open_dir}': {all_open_images}") # DEBUG

                        if all_open_images:
                            # Found one or more images, use the first one found
                            open_image_path = os.path.join(open_dir, all_open_images[0])
                            if len(all_open_images) > 1:
                                print(f"    -> (finalize) Warning: Found multiple images in '{open_dir}': {all_open_images}. Using the first one: {os.path.basename(open_image_path)}") # WARN line
                            else:
                                print(f"    -> (finalize) Found one open image: {os.path.basename(open_image_path)}. Using this path.") # INFO line
                            return open_image_path
                        else: # len(all_open_images) == 0
                            print(f"    -> (finalize) No image files found in corresponding 'open' directory: {open_dir}. Returning closed image '{closed_filename}'.") # INFO line
                            return base_path # Fallback to closed if none found
                    except Exception as e:
                        print(f"    -> (finalize) Error during find_corresponding_open_image logic: {e}. Returning closed path.")
                        return base_path
                # --- End Helper ---

                # Derive 'open' path if applicable, based on context
                if speaker_context == 'host_speaking':
                    host_path_to_use = find_corresponding_open_image(host_base_path)
                    print(f"    -> Using HOST: {os.path.basename(host_path_to_use)}, GUEST: {os.path.basename(guest_path_to_use)}")
                elif speaker_context == 'guest_speaking':
                    guest_path_to_use = find_corresponding_open_image(guest_base_path)
                    print(f"    -> Using HOST: {os.path.basename(host_path_to_use)}, GUEST: {os.path.basename(guest_path_to_use)}")
                elif speaker_context in ['intro_outro', 'none']:
                    print(f"    -> Context '{speaker_context}'. Using HOST CLOSED ({os.path.basename(host_path_to_use)}) and GUEST CLOSED ({os.path.basename(guest_path_to_use)}) images.")

                # Update the copied details with the final paths to be saved
                details['host_image'] = host_path_to_use
                details['guest_image'] = guest_path_to_use
                # --- End Image Path Determination ---


                # For speech segments, find the preceding silence file if applicable
                if segment_type == 'speech':
                    original_index = details.get('original_index')
                    if original_index is not None and original_index > 0 and original_index < len(self.all_segment_files):
                        potential_silence_path = self.all_segment_files[original_index - 1]
                        if ('silence' in os.path.basename(potential_silence_path).lower() and
                            os.path.exists(potential_silence_path)):
                            print(f"DEBUG: Adding silence before segment {i}: {os.path.basename(potential_silence_path)}")
                            self.final_structured_details.append({
                                'type': 'silence',
                                'audio_path': potential_silence_path
                            })

                # Append the potentially modified segment details (intro, speech, or outro)
                self.final_structured_details.append(details) # Append the modified copy

        self.root.quit() # Quit mainloop
        plt.close(self.fig) # Close matplotlib figure
        # Don't destroy here, let run() handle it after mainloop finishes

    # Removed get_final_segments, finalize now returns structured data via run()

    def run(self):
        self.root.mainloop()
        print("TTSDevGUI: Mainloop finished.")
        # Retrieve the structured details populated by finalize() or set to None by on_closing()
        final_structured_data = getattr(self, 'final_structured_details', None)
        try:
            # Ensure cleanup happens even if mainloop exits unexpectedly
            if self.player:
                self.player.cleanup()
            plt.close(self.fig) # Close plot figure
            self.root.destroy() # Destroy window after mainloop finishes
            print("TTSDevGUI: Window destroyed.")
        except tk.TclError as e:
            print(f"TTSDevGUI: Error destroying window (maybe already destroyed): {e}")
        # Return the list captured before destroy, or None if cancelled via on_closing
        return final_structured_data

# Modified dev_mode_process
def dev_mode_process(all_segment_files, reviewable_indices, text_segments_for_dev, api_host, api_port, speed, temp_dir, host_voice, guest_voice): # Added host_voice, guest_voice
    """
    Handle development mode GUI review process.

    Args:
        all_segment_files: List containing ALL file paths (speech and silence).
        reviewable_indices: List of indices in all_segment_files that correspond to speech segments.
        host_voice (str): The voice designated as the host.
        guest_voice (str): The voice designated as the guest.
        text_segments_for_dev: List of (text, voice, padding_ms) tuples, matching the order of reviewable_indices. # Updated tuple structure
        api_host: API host.
        api_port: API port.
        speed: Speech speed.
        temp_dir: Temporary directory path.

    Returns:
        List of file paths (potentially updated) including silence, or None if cancelled/failed.
    """
    if not all_segment_files:
        print("Dev Mode: No segments (speech or silence) provided!")
        return all_segment_files # Return empty list

    if not reviewable_indices:
        print("Dev Mode: No reviewable speech segments found, skipping GUI.")
        # If only silence was generated? Return the original list.
        return all_segment_files

    if len(reviewable_indices) != len(text_segments_for_dev):
         print(f"Dev Mode: Error - Mismatch between reviewable indices ({len(reviewable_indices)}) and text segment info ({len(text_segments_for_dev)}).")
         messagebox.showerror("Internal Error", "Mismatch in segment data for Dev Mode.")
         return None # Indicate failure

    if not pygame or not pygame.mixer.get_init():
         messagebox.showerror("Error", "Pygame not installed or failed to initialize. Cannot run Dev Mode GUI.")
         return None # Indicate failure

    print("Starting Dev Mode GUI...")
    gui = TTSDevGUI(api_host, api_port, speed, host_voice, guest_voice) # Pass voices
    gui.set_temp_dir(temp_dir) # Pass temp_dir for regeneration
    gui.set_all_segment_files(all_segment_files) # Give GUI the original list (needed for redo fallback?)

    # --- Populate GUI with Intro, Speech, Outro ---
    # 1. Add Intro
    gui.add_special_segment('intro')

    # 2. Add Speech Segments
    speech_gui_start_index = gui.segment_listbox.size() # Get index where speech segments start
    for review_list_idx, original_idx in enumerate(reviewable_indices):
        if original_idx < len(all_segment_files) and review_list_idx < len(text_segments_for_dev):
            file_path = all_segment_files[original_idx]
            # Unpack text, voice, and padding_ms
            text, voice, padding_ms = text_segments_for_dev[review_list_idx]
            # Pass original_index relative to all_segment_files, speech audio path, text, voice, and padding_ms
            gui.add_reviewable_segment(original_idx, file_path, text, voice, padding_ms=padding_ms) # Pass padding_ms
        else:
             print(f"Dev Mode: Warning - Index mismatch adding speech segment. Review Idx: {review_list_idx}, Original Idx: {original_idx}")

    # 3. Add Outro
    gui.add_special_segment('outro')

    # Run the GUI - this blocks until finalize or close
    # It returns the potentially modified all_segment_files list, or None if cancelled
    final_list = gui.run()
    return final_list


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

# Modified generate_audio_segment to use load_voice_config
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
                           norm_gauss_size=None): # Explicit gauss size or None
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
            # Try OpenAI-compatible endpoint first
            print(f"-> Trying OpenAI-compatible endpoint at {api_url}")
            response = requests.post(api_url, json=payload, headers=headers, timeout=180)
            response.raise_for_status()
        except (requests.exceptions.HTTPError, requests.exceptions.RequestException) as api_err:
            print(f"!! OpenAI-compatible endpoint failed: {api_err}")
            if response and response.text:
                print(f"Response content: {response.text}")
            
            print("!! Attempting legacy endpoint fallback...")
            response = None
            
            # Fallback to legacy endpoint
            legacy_url = f"http://{api_host}:{api_port}/speak"
            legacy_payload = {
                "text": input_text,
                "voice": voice
            }
            try:
                print(f"-> Trying legacy endpoint at {legacy_url}")
                response = requests.post(legacy_url, json=legacy_payload, headers=headers, timeout=180)
                response.raise_for_status()
            except requests.exceptions.RequestException as legacy_err:
                print(f"!! Legacy endpoint also failed: {legacy_err}")
                if response and response.text:
                    print(f"Response content: {response.text}")
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
                        import shutil # Import here if only used in this block
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
                from scipy.signal import resample
                data = resample(data, n_samples)
                print(f"-> Resampling complete. New length: {len(data)/target_samplerate:.2f}s")

            data, sr = sf.read(filepath, dtype='float32')

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

# Need to capture result of dev_mode_process to check for None
dev_mode_process_result = [] # Initialize as empty list

if __name__ == "__main__":
    # Define choices based on documentation
    # Language/Voice data structures defined at module level now

    parser = argparse.ArgumentParser(
        description="Generate speech from text or a script file using Orpheus TTS FastAPI endpoint.",
        epilog="Examples:\n"
               "  Single sentence: python3 test_orpheus_tts.py --input \"Hello there.\" --voice leo --output single\n"
               "  From script:   python3 test_orpheus_tts.py --script podcast.txt --host-voice leo --guest-voice tara --output podcast_audio.wav --silence 0.5\n"
               "  Dev Mode:      python3 test_orpheus_tts.py --script podcast.txt --dev --output dev_test.wav --silence 0.5\n"
               "  Expanded:      python3 orpheus_tts.py   --script podcast_script_small.txt   --host-voice leo   --guest-voice tara   --output simple_test_script   --dev   --guest-breakup   --video-resolution \"1920x1080\"   --video-fps 24   --video-intermediate-preset slow   --video-intermediate-crf 18   --video-final-audio-bitrate 320k",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # --- Input Arguments (Mutually Exclusive) ---
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--input', type=str, help='Single text input to synthesize.')
    group.add_argument('--script', type=str, help='Path to a script file (.txt) with lines like "Speaker: Dialogue".')

    # --- Script Specific Arguments ---
    # Choices removed as they are now language-dependent and primarily handled in GUI
    parser.add_argument('--host-voice', type=str, default='leo', # Removed choices=VOICES
                        help='Voice to use for lines starting with "Host:" (script mode only, default: leo).')
    parser.add_argument('--guest-voice', type=str, default='tara', # Removed choices=VOICES
                        help='Voice to use for lines starting with "Guest:" (script mode only, default: tara).')
    parser.add_argument('--silence', type=float, default=1.0,
                        help='Duration of silence in seconds between script lines (default: 1.0). Use 0 to disable.')

    # --- General Arguments ---
    # Choices removed as they are now language-dependent and primarily handled in GUI
    parser.add_argument('--voice', type=str, default='tara', # Removed choices=VOICES
                        help='Voice to use for single --input (default: tara).')
    parser.add_argument('--speed', type=float, default=1.0,
                        help='Speech speed factor (0.5 to 1.5, default: 1.0).')
    parser.add_argument('--port', type=int, default=5005,
                        help='Port the Orpheus-FastAPI server is running on (default: 5005).')
    parser.add_argument('--api-host', type=str, default='127.0.0.1', # Renamed from --host
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


    args = parser.parse_args()

    # --- Main Logic ---
    # Create dedicated directories for outputs and temporary audio
    OUTPUT_DIR = "outputs"
    TEMP_AUDIO_DIR = "temp_audio"
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(TEMP_AUDIO_DIR, exist_ok=True)
    # Use TEMP_AUDIO_DIR for temporary files instead of system default
    temp_dir = TEMP_AUDIO_DIR # Assign TEMP_AUDIO_DIR to temp_dir variable used by functions
    print(f"Using temporary audio directory: {temp_dir}")
    print(f"Saving final outputs to: {OUTPUT_DIR}")


    all_segment_files = [] # List to hold final sequence of files (speech + silence)
    reviewable_indices = [] # List of indices in all_segment_files that are speech segments
    text_segments_for_dev = []  # Store (text, voice) pairs ONLY for reviewable segments
    success = False
    target_sr = None # Will be determined by the first successful segment


    try:
        if args.input:
            # Single input mode
            # generate_audio_segment now loads gain from config by default
            temp_file, generated_sr = generate_audio_segment(
                args.input, args.voice, args.speed, args.api_host, args.port, temp_dir
                # gain_factor is not passed, so it will use the default from the loaded config
            )
            if temp_file:
                current_index = len(all_segment_files)
                all_segment_files.append(temp_file) # Add to the main list
                reviewable_indices.append(current_index) # Mark this index as reviewable
                target_sr = generated_sr # Set sample rate from the generated file
                text_segments_for_dev.append((args.input, args.voice)) # Track text/voice for dev mode

                # If not dev mode, just copy the single file to output immediately
                if not args.dev:
                    print(f"\nCopying single segment to {args.output}...")
                    try:
                        # Ensure final output path is in OUTPUT_DIR
                        output_path = os.path.join(OUTPUT_DIR, args.output)
                        # Copy the temp file to the final output path
                        import shutil # Ensure shutil is imported
                        shutil.copy2(temp_file, output_path)
                        print(f"✅ Audio saved successfully to '{output_path}'")
                        success = True
                    except Exception as e:
                        print(f"!! Error copying temp file {temp_file} to {output_path}: {e}")
                # If dev mode, processing happens later
            else:
                print("!! Failed to generate audio for the input text.")

        elif args.script:
            # Script processing mode
            if not os.path.exists(args.script):
                print(f"!! Error: Script file not found: {args.script}")
                sys.exit(1)

            # --- Pre-process script to determine speakers and dialogue ---
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
                                    'original_line_index': i + 1 # Store 1-based index for logging
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

            # --- Define Padding Constants (ms) ---
            PADDING_SPEAKER_CHANGE_MS = 750
            PADDING_SAME_SPEAKER_MS = 100

            # --- Generate Segments with Calculated Padding ---
            first_segment_generated = False
            for idx, segment_data in enumerate(parsed_segments):
                speaker = segment_data['speaker']
                dialogue = segment_data['dialogue']
                line_num = segment_data['original_line_index']

                # Determine padding based on the *next* segment
                pad_ms = 0
                if idx + 1 < len(parsed_segments): # If not the last segment
                    next_speaker = parsed_segments[idx + 1]['speaker']
                    if speaker != next_speaker:
                        pad_ms = PADDING_SPEAKER_CHANGE_MS
                    else:
                        pad_ms = PADDING_SAME_SPEAKER_MS
                    print(f"  Segment {idx+1} (Line {line_num}): Next speaker is '{next_speaker}'. Padding = {pad_ms}ms")
                else:
                    print(f"  Segment {idx+1} (Line {line_num}): Last segment. Padding = 0ms")


                # --- Guest Breakup Logic (Integrated) ---
                if speaker == "guest" and args.guest_breakup:
                    sentences = [dialogue] # Default
                    try:
                        try: nltk.data.find('tokenizers/punkt')
                        except LookupError:
                            print("NLTK 'punkt' tokenizer not found. Attempting download...")
                            nltk.download('punkt')
                            print("Download complete (if successful).")
                        try: sentences = nltk.sent_tokenize(dialogue)
                        except Exception as tokenize_err:
                             print(f"!! NLTK Error tokenizing line {line_num}: {tokenize_err}. Processing as single segment.")
                             sentences = [dialogue] # Fallback
                    except Exception as nltk_e:
                        print(f"!! Error with NLTK setup for line {line_num}: {nltk_e}. Processing as single segment.")

                    print(f"-> Breaking Guest line {line_num} into chunks (up to 2 sentences).")
                    num_sub_segments = (len(sentences) + 1) // 2
                    for sub_idx in range(num_sub_segments):
                        sent_idx = sub_idx * 2
                        sentence1 = sentences[sent_idx].strip() if sent_idx < len(sentences) else ""
                        combined_text = sentence1
                        sentence2 = sentences[sent_idx + 1].strip() if sent_idx + 1 < len(sentences) else ""
                        if sentence1 and sentence2: combined_text += " " + sentence2
                        elif sentence2: combined_text = sentence2

                        if not combined_text: continue # Skip empty sub-segments

                        # Determine padding for this sub-segment
                        # Pad with 'same speaker' between sub-segments
                        # Pad with calculated 'pad_ms' only after the *last* sub-segment
                        sub_pad_ms = PADDING_SAME_SPEAKER_MS if sub_idx < num_sub_segments - 1 else pad_ms

                        # --- Generation (Sub-segment) ---
                        voice = args.guest_voice
                        # initial_gain removed, generate_audio_segment loads it
                        temp_file, generated_sr = generate_audio_segment(
                            combined_text, voice, args.speed, args.api_host, args.port, temp_dir,
                            pad_end_ms=sub_pad_ms # Pass sub-segment padding explicitly
                            # gain_factor is not passed, uses default from config
                        )

                        # --- Process Result (Sub-segment) ---
                        if temp_file:
                            if not first_segment_generated:
                                target_sr = generated_sr
                                print(f"--- Target sample rate set to {target_sr} Hz ---")
                                first_segment_generated = True
                            elif generated_sr != target_sr:
                                print(f"!! Warning: Samplerate mismatch ({generated_sr} Hz) for sub-segment {sub_idx+1} of line {line_num}. Skipping.")
                                if os.path.exists(temp_file): os.remove(temp_file)
                                continue # Skip this sub-segment

                            # Add sub-segment speech file
                            current_index = len(all_segment_files)
                            all_segment_files.append(temp_file)
                            reviewable_indices.append(current_index)
                            # Pass sub_pad_ms to store the padding for this sub-segment
                            text_segments_for_dev.append((combined_text, voice, sub_pad_ms)) # Store padding with text/voice
                        else:
                            print(f"!! Warning: Failed to generate sub-segment {sub_idx+1} for line {line_num}. Skipping.")
                else:
                    # --- Original Logic (Host or Guest without --guest-breakup) ---
                    voice = args.host_voice if speaker == "host" else args.guest_voice
                    # initial_gain removed, generate_audio_segment loads it
                    temp_file, generated_sr = generate_audio_segment(
                        dialogue, voice, args.speed, args.api_host, args.port, temp_dir,
                        pad_end_ms=pad_ms # Pass calculated padding explicitly
                        # gain_factor is not passed, uses default from config
                    )

                    if temp_file:
                        if not first_segment_generated:
                            target_sr = generated_sr
                            print(f"--- Target sample rate set to {target_sr} Hz ---")
                            first_segment_generated = True
                        elif generated_sr != target_sr:
                            print(f"!! Warning: Samplerate mismatch ({generated_sr} Hz) for line {line_num}. Skipping segment.")
                            if os.path.exists(temp_file): os.remove(temp_file)
                            continue # Skip appending this segment

                        # Add speech segment
                        current_index = len(all_segment_files)
                        all_segment_files.append(temp_file)
                        reviewable_indices.append(current_index) # Mark index as reviewable
                        # Pass pad_ms to store the padding for this segment
                        text_segments_for_dev.append((dialogue, voice, pad_ms)) # Store padding with text/voice
                    else:
                        print(f"!! Warning: Failed to generate segment for line {line_num}. Skipping.")

            # Silence files are no longer added separately

        # --- Processing based on mode ---
        files_to_concatenate = []
        if args.dev:
            if reviewable_indices: # Only enter dev mode if there's something to review
                 print("\nEntering development mode for segment review...")
                 # Pass the full list, indices of reviewable items, and their text/voice/padding
                 dev_mode_process_result = dev_mode_process(
                     all_segment_files,
                     reviewable_indices,
                     text_segments_for_dev, # Now contains (text, voice, padding_ms) tuples
                     args.api_host, args.port, args.speed, temp_dir, args.host_voice, args.guest_voice # Pass voices
                 )

                 if dev_mode_process_result is not None: # GUI finished without cancel/error
                     print("Development mode finished. Processing final segments...")
                     if dev_mode_process_result:
                         print(f"Found {len(dev_mode_process_result)} segments with audio and visual details")
                         
                         # Use the main OUTPUT_DIR for the podcast audio sub-directory
                         output_dir = os.path.join(OUTPUT_DIR, 'podcast_audio')
                         os.makedirs(output_dir, exist_ok=True)
                         print(f"Created podcast audio directory: {output_dir}")

                         # Copy audio files from temporary locations (TEMP_AUDIO_DIR) and update paths
                         print(f"\nProcessing {len(dev_mode_process_result)} segments for final JSON...")
                         for idx, segment in enumerate(dev_mode_process_result):
                             original_audio_path = segment.get('audio_path')
                             segment_type = segment.get('type', 'unknown')
                             print(f"  Segment {idx+1} ({segment_type}): Checking path '{original_audio_path}'")

                             # Check if the path is potentially temporary (in our temp_audio dir) and needs copying
                             # Use os.path.abspath for reliable checking
                             is_temporary = original_audio_path and os.path.abspath(TEMP_AUDIO_DIR) in os.path.abspath(original_audio_path)

                             if is_temporary:
                                 if os.path.exists(original_audio_path):
                                     try:
                                         new_name = os.path.basename(original_audio_path)
                                         new_path = os.path.join(output_dir, new_name)
                                         # Avoid unnecessary copy if destination already exists (e.g., from a previous run)
                                         if not os.path.exists(new_path) or os.path.getmtime(original_audio_path) > os.path.getmtime(new_path):
                                             import shutil
                                             shutil.copy2(original_audio_path, new_path)
                                             print(f"    -> Copied temp audio '{new_name}' to '{output_dir}'")
                                         else:
                                             print(f"    -> Audio '{new_name}' already exists in '{output_dir}', skipping copy.")
                                         # Update path in the segment data regardless of copy action
                                         segment['audio_path'] = new_path
                                         print(f"    -> Updated path to: {new_path}")
                                     except Exception as copy_err:
                                         print(f"    !! ERROR copying temp file '{original_audio_path}' to '{output_dir}': {copy_err}")
                                         print(f"    !! Keeping original temporary path in JSON for segment {idx+1}.")
                                 else:
                                     print(f"    !! WARNING: Temporary audio file '{original_audio_path}' not found! Cannot copy.")
                                     print(f"    !! Keeping original temporary path in JSON for segment {idx+1}.")
                             elif original_audio_path:
                                 # Path is not temporary, ensure it exists if it's not 'None' or similar placeholders
                                 if segment_type != 'intro' and segment_type != 'outro' and not os.path.exists(original_audio_path):
                                      # Allow intro/outro music to potentially be 'None' or non-existent without warning here
                                      # Check speech/silence paths more strictly
                                      if segment_type in ['speech', 'silence']:
                                           print(f"    !! WARNING: Non-temporary audio path '{original_audio_path}' does not exist for segment {idx+1} ({segment_type}).")
                                 else:
                                     print(f"    -> Path is not temporary or already processed.") # Indicates path is likely okay or already copied
                             else:
                                 print(f"    -> No audio path found for segment {idx+1} ({segment_type}).") # e.g., might be expected for intro/outro with no music selected

                         # Ensure JSON config path is within OUTPUT_DIR
                         json_config_path = os.path.join(OUTPUT_DIR, args.output + '.json')
                         with open(json_config_path, 'w') as f:
                             import json
                             json.dump(dev_mode_process_result, f, indent=2)
                         print(f"Saved structured segment details to {json_config_path}")

                         # --- Automatically Trigger Video Generation ---
                         print("\nAttempting to generate video from the finalized configuration...")
                         # Ensure video output path is also within OUTPUT_DIR
                         video_output_path = os.path.join(OUTPUT_DIR, args.output.rsplit('.', 1)[0] + '.mp4')

                         # Construct arguments for the video generator using args from this script
                         video_args = argparse.Namespace(
                             config_json=json_config_path,
                             output_video=video_output_path,
                             character_scale=args.video_character_scale,
                             resolution=args.video_resolution,
                             video_fade=args.video_fade,
                             # audio_fadein/out are not directly controlled here, defaults in videov4 used
                             audio_fadein=5.0, # Keep default or add args if needed
                             audio_fadeout=5.0,# Keep default or add args if needed
                             fps=args.video_fps,
                             intermediate_preset=args.video_intermediate_preset,
                             intermediate_crf=args.video_intermediate_crf,
                             final_audio_bitrate=args.video_final_audio_bitrate,
                             workers=args.video_workers, # Pass None to let videov4 handle default
                             keep_temp_files=args.video_keep_temp
                         )

                         try:
                             print(f"Calling video generator with args: {vars(video_args)}")
                             # generate_video(video_args.config_json, video_args.output_video, video_args) # Disabled as generate_podcast_videov4 is removed
                             print(f"Video generation process initiated for {video_output_path}.")
                             # Note: generate_video handles its own success/failure printing.
                             # We mark success based on JSON creation, video is best-effort here.
                             success = True
                         except Exception as video_e:
                             print(f"!! Error calling generate_podcast_videov4.main: {video_e}")
                             success = False # Consider if failure to start video gen should fail the whole process

                 else: # dev_mode_process_result was None
                     print("!! Development mode cancelled or failed to initialize. No output generated.")
                     success = False # Ensure success is false if GUI fails/cancels
            else:
                 print("!! No audio segments were generated to review in development mode.")
                 # If only silence was generated, should we concatenate it? Probably not.
                 success = False
        elif all_segment_files: # Not dev mode, and we have files (speech and/or silence)
            print("\nDev mode not enabled. Concatenating initial segments (no Intro/Outro)...")
            # Need to build a basic structured list for finalize_audio_sequence
            # This assumes the original structure: Speech, Silence, Speech, Silence...
            basic_structured_details = []
            for file_path in all_segment_files:
                segment_type = 'silence' if 'silence' in os.path.basename(file_path).lower() else 'speech'
                basic_structured_details.append({'type': segment_type, 'audio_path': file_path})
            # Ensure final non-dev output goes to the OUTPUT_DIR
            final_output_path = os.path.join(OUTPUT_DIR, args.output)
            # Call concatenate_wavs directly for non-dev mode
            files_to_concatenate = [d['audio_path'] for d in basic_structured_details if d.get('audio_path')]
            success = concatenate_wavs(files_to_concatenate, final_output_path, target_sr)
        else: # Not dev mode, and no files generated
            print("!! No audio segments were generated successfully.")


    finally:
        # --- Cleanup ---
        # Cleanup the dedicated TEMP_AUDIO_DIR
        print(f"\nCleaning up temporary audio directory: {TEMP_AUDIO_DIR}...")
        try:
            import shutil # Ensure shutil is imported
            # Check if the directory exists before attempting removal
            if os.path.isdir(TEMP_AUDIO_DIR):
                shutil.rmtree(TEMP_AUDIO_DIR)
                print(f"-> Temporary audio directory {TEMP_AUDIO_DIR} removed.")
            else:
                print(f"-> Temporary audio directory {TEMP_AUDIO_DIR} does not exist, skipping removal.")
        except Exception as e:
            print(f"!! Warning: Error cleaning up temporary audio directory {TEMP_AUDIO_DIR}: {e}")


        # Quit pygame mixer if initialized
        if pygame and pygame.mixer.get_init():
            print("Quitting pygame mixer...")
            pygame.mixer.quit()

        if success:
            print("\nProcessing complete.")
        else:
            print("\nProcessing finished with errors or was cancelled.")
            # Exit with error status if processing failed or dev mode was cancelled/errored
            # Check if dev_mode_process_result exists before accessing
            dev_result_is_none = 'dev_mode_process_result' in locals() and dev_mode_process_result is None
            if not success and (not args.dev or dev_result_is_none):
                 print("Exiting with status 1 due to error or cancellation.")
                 sys.exit(1)

