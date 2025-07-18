import tkinter as tk
from tkinter import ttk, scrolledtext, Canvas
import os
import glob
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import sys

# Override print function to force immediate flushing for real-time output
original_print = print
def print(*args, **kwargs):
    kwargs.setdefault('flush', True)
    return original_print(*args, **kwargs)

# Import functions from other modules
from functions.tts.api import generate_audio_segment
from functions.tts.utils import load_voice_config, generate_silence, concatenate_wavs
from functions.tts.gui.player import AudioPlayer
from functions.tts.args import LANGUAGES_VOICES, LANGUAGES
from functions.tts.gui import handlers # Import the new handlers module
from functions.tts.gui import widgets # Import the new widgets module

# Constants
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..', '..'))
IMAGE_DIR = os.path.abspath(os.path.join(PROJECT_ROOT, "settings/images"))
MUSIC_DIR = os.path.abspath(os.path.join(PROJECT_ROOT, "settings/music"))

DEFAULT_BG = os.path.join(IMAGE_DIR, "background/Podcast_Background.png")
NO_MUSIC = "None"
NO_IMAGE = "None"

try:
    from pydub import AudioSegment
    pydub_available = True
except ImportError:
    pydub_available = False

class TTSDevGUI:
    def __init__(self, api_host, api_port, speed, host_voice, guest_voice):
        self.root = tk.Tk()
        self.root.title("TTS Development Interface - Visual & Audio")
        self.root.geometry("1200x800")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.api_host = api_host
        self.api_port = api_port
        self.speed = speed
        self.host_voice = host_voice
        self.guest_voice = guest_voice
        self.final_structured_details = None

        # Load Image and Music Files
        self.background_files = [DEFAULT_BG] if os.path.exists(DEFAULT_BG) else []
        self.background_files += sorted(glob.glob(os.path.join(IMAGE_DIR, "background", "*.*")))

        def load_character_images(char_type):
            open_dir = os.path.join(IMAGE_DIR, char_type, "open")
            closed_dir = os.path.join(IMAGE_DIR, char_type, "closed")
            open_files = [NO_IMAGE] + sorted(glob.glob(os.path.join(open_dir, "*.*"))) if os.path.isdir(open_dir) else [NO_IMAGE]
            closed_files = [NO_IMAGE] + sorted(glob.glob(os.path.join(closed_dir, "*.*"))) if os.path.isdir(closed_dir) else [NO_IMAGE]
            open_files = sorted(list(set(f for f in open_files if f == NO_IMAGE or os.path.isfile(f))))
            closed_files = sorted(list(set(f for f in closed_files if f == NO_IMAGE or os.path.isfile(f))))
            return open_files, closed_files

        self.host_open_image_files, self.host_closed_image_files = load_character_images("host")
        self.guest_open_image_files, self.guest_closed_image_files = load_character_images("guest")

        self.intro_music_files = [NO_MUSIC] + sorted(glob.glob(os.path.join(MUSIC_DIR, "intro", "*.*")))
        self.outro_music_files = [NO_MUSIC] + sorted(glob.glob(os.path.join(MUSIC_DIR, "outro", "*.*")))

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
        self.reviewable_segment_details = {}
        self.gui_index_to_original_index = {} # Maps GUI listbox index to index in all_segment_files

        # Initialize Tkinter Variables
        self.language_var = tk.StringVar()
        self.voice_var = tk.StringVar()
        self.progress_var = tk.DoubleVar(value=0)
        self.gain_var = tk.DoubleVar(value=1.0)
        self.bg_image_var = tk.StringVar()
        self.host_image_var = tk.StringVar()
        self.guest_image_var = tk.StringVar()
        self.intro_music_var = tk.StringVar()
        self.outro_music_var = tk.StringVar()

        # New variables for processing options
        self.ffmpeg_enhancement_var = tk.BooleanVar(value=True)
        self.deesser_var = tk.BooleanVar(value=True)
        self.deesser_freq_var = tk.IntVar(value=5000)
        self.trim_end_ms_var = tk.IntVar(value=120)
        self.padding_ms_var = tk.IntVar(value=0)
        # FFmpeg parameter variables
        self.nr_level_var = tk.IntVar(value=35)
        self.compress_thresh_var = tk.DoubleVar(value=0.03)
        self.compress_ratio_var = tk.IntVar(value=2)
        self.norm_frame_len_var = tk.IntVar(value=20)
        self.norm_gauss_size_var = tk.IntVar(value=15)

        # State Variables
        self.current_gui_selection = None
        self.temp_dir = None

        # Matplotlib waveform plot elements
        self.fig, self.ax = plt.subplots(figsize=(5, 1.5))
        self.fig.tight_layout()
        self.waveform_canvas_agg = None
        self.player = None
        self.preview_canvas = None
        self.bg_photo_image = None
        self.host_photo_image = None
        self.guest_photo_image = None
        self.bg_canvas_id = None
        self.host_canvas_id = None
        self.guest_canvas_id = None

        # Bind keyboard shortcuts
        self.root.bind('<Control-r>', lambda e: handlers.redo_segment(self))
        self.root.bind('<Escape>', lambda e: self.player.stop() if self.player else None)

        # Create main layout
        self.create_widgets()

    def set_temp_dir(self, temp_dir):
        self.temp_dir = temp_dir

    def set_all_segment_files(self, all_files):
        self.all_segment_files = list(all_files)

    def on_closing(self):
        """Handle window close button"""
        print("TTSDevGUI: Closing window.")
        if self.player:
            self.player.cleanup()
        self.final_structured_details = None
        self.root.quit()
        plt.close(self.fig)
        self.root.destroy()

    def create_widgets(self):
        # Configure Root Window Grid
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1) # Left frame column
        self.root.grid_columnconfigure(1, weight=3) # Right frame column (more space)

        # Left Panel (Segment List)
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
        self.segment_listbox.bind('<<ListboxSelect>>', lambda e: handlers.on_segment_select(self, e))

        # Right Panel (Main Container)
        right_main_frame = ttk.Frame(self.root)
        right_main_frame.grid(row=0, column=1, sticky='nsew', padx=5, pady=5)
        right_main_frame.grid_rowconfigure(0, weight=1) # Allow row to expand vertically
        right_main_frame.grid_columnconfigure(0, weight=3) # Controls frame (more weight)
        right_main_frame.grid_columnconfigure(1, weight=1) # Preview frame (less weight)

        # Right-Left Sub-panel (Controls, Text, Waveform, Player)
        right_left_frame = ttk.Frame(right_main_frame)
        right_left_frame.grid(row=0, column=0, sticky='nsew', padx=(0, 5))
        # Configure rows for expansion
        right_left_frame.grid_columnconfigure(0, weight=1) # Allow content to expand horizontally
        right_left_frame.grid_rowconfigure(1, weight=2)  # Text Display row
        right_left_frame.grid_rowconfigure(3, weight=3)  # Waveform row

        # Right-Right Sub-panel (Visual Preview)
        right_right_frame = ttk.Frame(right_main_frame)
        right_right_frame.grid(row=0, column=1, sticky='nsew', padx=(5, 0))
        # Let the canvas determine the height, don't give the row extra weight
        right_right_frame.grid_rowconfigure(0, weight=0) # Label row
        right_right_frame.grid_rowconfigure(1, weight=0) # Canvas row should NOT expand vertically beyond its needs
        right_right_frame.grid_columnconfigure(0, weight=1) # Allow canvas to expand horizontally

        # 0. Visual Preview (in right_right_frame)
        ttk.Label(right_right_frame, text="Visual Preview:").grid(row=0, column=0, sticky='w', pady=(0, 2))
        self.preview_canvas = Canvas(right_right_frame, bg='grey', borderwidth=1, relief="sunken")
        self.preview_canvas.grid(row=1, column=0, sticky='new', pady=5)
        self.preview_canvas.bind("<Configure>", lambda e: widgets.on_preview_resize(self, e))
        self.root.after(100, lambda: widgets.on_preview_resize(self, None))

        # Widgets in right_left_frame
        current_row = 0

        # Title label for selected segment
        self.selected_segment_label = ttk.Label(right_left_frame, text="No Segment Selected", font=('Helvetica', 12, 'bold'))
        self.selected_segment_label.grid(row=current_row, column=0, sticky='w', pady=(5, 2))
        current_row += 1

        # 1. Text Display
        self.text_display = scrolledtext.ScrolledText(right_left_frame, height=8, wrap=tk.WORD)
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
        self.language_combo.bind('<<ComboboxSelected>>', lambda e: handlers.handle_language_change(self, e))
        sel_row += 1

        # 2b. Voice Selector
        ttk.Label(selection_frame, text="Voice:", width=10).grid(row=sel_row, column=0, sticky='w', padx=5, pady=2)
        self.voice_combo = ttk.Combobox(selection_frame, textvariable=self.voice_var,
                                       values=[], state='readonly') # Values set dynamically
        self.voice_combo.grid(row=sel_row, column=1, sticky='ew', padx=5, pady=2)
        self.voice_combo.bind('<<ComboboxSelected>>', lambda e: handlers.handle_voice_change(self, e))
        sel_row += 1

        # 2c. Background Image Selector
        ttk.Label(selection_frame, text="Background:", width=10).grid(row=sel_row, column=0, sticky='w', padx=5, pady=2)
        self.bg_combo = ttk.Combobox(selection_frame, textvariable=self.bg_image_var,
                                     values=self.background_names, state='readonly')
        self.bg_combo.grid(row=sel_row, column=1, sticky='ew', padx=5, pady=2)
        self.bg_combo.bind('<<ComboboxSelected>>', lambda e: handlers.handle_bg_change(self, e))
        sel_row += 1

        # 2d. Host Image Selector
        ttk.Label(selection_frame, text="Host Img:", width=10).grid(row=sel_row, column=0, sticky='w', padx=5, pady=2)
        self.host_img_combo = ttk.Combobox(selection_frame, textvariable=self.host_image_var,
                                           values=self.host_closed_image_names, state='readonly')
        self.host_img_combo.grid(row=sel_row, column=1, sticky='ew', padx=5, pady=2)
        self.host_img_combo.bind('<<ComboboxSelected>>', lambda e: handlers.handle_host_img_change(self, e))
        sel_row += 1

        # 2e. Guest Image Selector
        ttk.Label(selection_frame, text="Guest Img:", width=10).grid(row=sel_row, column=0, sticky='w', padx=5, pady=2)
        self.guest_img_combo = ttk.Combobox(selection_frame, textvariable=self.guest_image_var,
                                            values=self.guest_closed_image_names, state='readonly')
        self.guest_img_combo.grid(row=sel_row, column=1, sticky='ew', padx=5, pady=2)
        self.guest_img_combo.bind('<<ComboboxSelected>>', lambda e: handlers.handle_guest_img_change(self, e))
        sel_row += 1

        # 2f. Intro Music Selector
        ttk.Label(selection_frame, text="Intro Music:", width=10).grid(row=sel_row, column=0, sticky='w', padx=5, pady=2)
        self.intro_music_combo = ttk.Combobox(selection_frame, textvariable=self.intro_music_var,
                                              values=self.intro_music_names, state='readonly')
        self.intro_music_combo.grid(row=sel_row, column=1, sticky='ew', padx=5, pady=2)
        self.intro_music_combo.bind('<<ComboboxSelected>>', lambda e: handlers.handle_intro_music_change(self, e))
        if not pydub_available: self.intro_music_combo.config(state=tk.DISABLED)
        sel_row += 1

        # 2g. Outro Music Selector
        ttk.Label(selection_frame, text="Outro Music:", width=10).grid(row=sel_row, column=0, sticky='w', padx=5, pady=2)
        self.outro_music_combo = ttk.Combobox(selection_frame, textvariable=self.outro_music_var,
                                              values=self.outro_music_names, state='readonly')
        self.outro_music_combo.grid(row=sel_row, column=1, sticky='ew', padx=5, pady=2)
        self.outro_music_combo.bind('<<ComboboxSelected>>', lambda e: handlers.handle_outro_music_change(self, e))
        if not pydub_available: self.outro_music_combo.config(state=tk.DISABLED)
        sel_row += 1

        # Audio Processing Options (within selection_frame)
        processing_frame = ttk.LabelFrame(selection_frame, text="Audio Processing")
        processing_frame.grid(row=sel_row, column=0, columnspan=2, sticky='ew', padx=5, pady=(10, 2))
        processing_frame.grid_columnconfigure(0, weight=0)
        processing_frame.grid_columnconfigure(1, weight=1)
        sel_row += 1
        proc_row = 0 # Internal row counter for processing_frame

        # 2h. FFmpeg Enhancement Toggle
        self.ffmpeg_check = ttk.Checkbutton(processing_frame, text="Apply FFmpeg Enhancement (NR, Norm, De-ess)",
                                             variable=self.ffmpeg_enhancement_var,
                                             command=lambda: handlers.handle_ffmpeg_change(self))
        self.ffmpeg_check.grid(row=proc_row, column=0, columnspan=2, sticky='w', padx=5, pady=(2,0))
        proc_row += 1

        # De-esser Frame (within processing_frame)
        deesser_frame = ttk.Frame(processing_frame)
        deesser_frame.grid(row=proc_row, column=0, columnspan=2, sticky='ew', padx=5, pady=2)
        deesser_frame.grid_columnconfigure(2, weight=1)
        proc_row += 1

        self.deesser_check = ttk.Checkbutton(deesser_frame, text="Apply De-esser",
                                        variable=self.deesser_var,
                                        command=lambda: handlers.handle_deesser_change(self))
        self.deesser_check.grid(row=0, column=0, sticky='w', padx=5)

        ttk.Label(deesser_frame, text="Frequency (Hz):").grid(row=0, column=1, sticky='w', padx=(10, 2))
        self.deesser_freq_spinbox = ttk.Spinbox(deesser_frame, from_=3000, to=10000, increment=500,
                                              textvariable=self.deesser_freq_var, width=6,
                                              command=lambda: handlers.handle_ffmpeg_param_change(self))
        self.deesser_freq_var.trace_add("write", lambda *args: handlers.handle_ffmpeg_param_change_trace(self, *args))
        self.deesser_freq_spinbox.grid(row=0, column=2, sticky='w', padx=5)

        # 2i. Trim End Control
        trim_frame = ttk.Frame(processing_frame)
        trim_frame.grid(row=proc_row, column=0, columnspan=2, sticky='ew', padx=5, pady=2)
        trim_frame.grid_columnconfigure(1, weight=1)
        proc_row += 1
        ttk.Label(trim_frame, text="Trim End (ms):", width=15).grid(row=0, column=0, sticky='w', padx=5)
        self.trim_spinbox = ttk.Spinbox(trim_frame, from_=0, to=1000, increment=10,
                                        textvariable=self.trim_end_ms_var, width=6,
                                        command=lambda: handlers.handle_trim_change(self))
        self.trim_end_ms_var.trace_add("write", lambda *args: handlers.handle_trim_change_trace(self, *args))
        self.trim_spinbox.grid(row=0, column=1, sticky='w', padx=5)

        # 2j. Padding Control
        padding_frame = ttk.Frame(processing_frame)
        padding_frame.grid(row=proc_row, column=0, columnspan=2, sticky='ew', padx=5, pady=2)
        padding_frame.grid_columnconfigure(1, weight=1)
        proc_row += 1
        ttk.Label(padding_frame, text="End Padding (ms):", width=15).grid(row=0, column=0, sticky='w', padx=5)
        self.padding_spinbox = ttk.Spinbox(padding_frame, from_=0, to=5000, increment=50,
                                           textvariable=self.padding_ms_var, width=6,
                                           command=lambda: handlers.handle_padding_change(self))
        self.padding_ms_var.trace_add("write", lambda *args: handlers.handle_padding_change_trace(self, *args))
        self.padding_spinbox.grid(row=0, column=1, sticky='w', padx=5)

        # Separator
        ttk.Separator(processing_frame, orient=tk.HORIZONTAL).grid(row=proc_row, column=0, columnspan=2, sticky='ew', pady=(8, 4), padx=5)
        proc_row += 1

        # FFmpeg Parameter Controls (within processing_frame)
        self.ffmpeg_params_frame = ttk.Frame(processing_frame)
        self.ffmpeg_params_frame_grid_config = {'row': proc_row, 'column': 0, 'columnspan': 2, 'sticky': 'ew', 'padx': 5, 'pady': 2}
        
        ff_row = 0 # Internal row counter for ffmpeg_params_frame
        self.ffmpeg_params_frame.grid_columnconfigure(1, weight=1) # Allow controls to align

        # Noise Reduction Level
        ttk.Label(self.ffmpeg_params_frame, text="NR Level (0-97):", width=18).grid(row=ff_row, column=0, sticky='w', padx=5, pady=1)
        self.nr_spinbox = ttk.Spinbox(self.ffmpeg_params_frame, from_=0, to=97, increment=1, textvariable=self.nr_level_var, width=6, command=lambda: handlers.handle_ffmpeg_param_change(self), wrap=True)
        self.nr_level_var.trace_add("write", lambda *args: handlers.handle_ffmpeg_param_change_trace(self, *args))
        self.nr_spinbox.grid(row=ff_row, column=1, sticky='w', padx=5, pady=1)
        ff_row += 1

        # Compressor Threshold
        ttk.Label(self.ffmpeg_params_frame, text="Comp Thresh (0.001-1):", width=18).grid(row=ff_row, column=0, sticky='w', padx=5, pady=1)
        self.compress_thresh_entry = ttk.Entry(self.ffmpeg_params_frame, textvariable=self.compress_thresh_var, width=6)
        self.compress_thresh_var.trace_add("write", lambda *args: handlers.handle_ffmpeg_param_change_trace(self, *args))
        self.compress_thresh_entry.grid(row=ff_row, column=1, sticky='w', padx=5, pady=1)
        ff_row += 1

        # Compressor Ratio
        ttk.Label(self.ffmpeg_params_frame, text="Comp Ratio (1-20):", width=18).grid(row=ff_row, column=0, sticky='w', padx=5, pady=1)
        self.compress_ratio_spinbox = ttk.Spinbox(self.ffmpeg_params_frame, from_=1, to=20, increment=1, textvariable=self.compress_ratio_var, width=6, command=lambda: handlers.handle_ffmpeg_param_change(self), wrap=True)
        self.compress_ratio_var.trace_add("write", lambda *args: handlers.handle_ffmpeg_param_change_trace(self, *args))
        self.compress_ratio_spinbox.grid(row=ff_row, column=1, sticky='w', padx=5, pady=1)
        ff_row += 1

        # Normalization Frame Length
        ttk.Label(self.ffmpeg_params_frame, text="Norm Frame (10-8000):", width=18).grid(row=ff_row, column=0, sticky='w', padx=5, pady=1)
        self.norm_frame_spinbox = ttk.Spinbox(self.ffmpeg_params_frame, from_=10, to=8000, increment=10, textvariable=self.norm_frame_len_var, width=6, command=lambda: handlers.handle_ffmpeg_param_change(self), wrap=True)
        self.norm_frame_len_var.trace_add("write", lambda *args: handlers.handle_ffmpeg_param_change_trace(self, *args))
        self.norm_frame_spinbox.grid(row=ff_row, column=1, sticky='w', padx=5, pady=1)
        ff_row += 1

        # Normalization Gauss Size
        ttk.Label(self.ffmpeg_params_frame, text="Norm Gauss (3-301):", width=18).grid(row=ff_row, column=0, sticky='w', padx=5, pady=1)
        self.norm_gauss_spinbox = ttk.Spinbox(self.ffmpeg_params_frame, from_=3, to=301, increment=2, textvariable=self.norm_gauss_size_var, width=6, command=lambda: handlers.handle_ffmpeg_param_change(self), wrap=True)
        self.norm_gauss_size_var.trace_add("write", lambda *args: handlers.handle_ffmpeg_param_change_trace(self, *args))
        self.norm_gauss_spinbox.grid(row=ff_row, column=1, sticky='w', padx=5, pady=1)
        ff_row += 1

        # Initial state based on the main checkbox
        handlers._toggle_ffmpeg_params_visibility(self)

        # 3. Waveform Plot Area
        self.waveform_canvas_agg = FigureCanvasTkAgg(self.fig, master=right_left_frame)
        self.waveform_canvas_agg.mpl_connect('button_press_event', lambda e: handlers.on_waveform_click(self, e))
        self.waveform_canvas_widget = self.waveform_canvas_agg.get_tk_widget()
        self.waveform_canvas_widget.grid(row=current_row, column=0, sticky='nsew', pady=5)
        current_row += 1

        # 4. Audio Player Instance
        self.player = AudioPlayer(right_left_frame, redo_command=lambda: handlers.redo_segment(self), waveform_ax=self.ax, waveform_canvas_agg=self.waveform_canvas_agg)
        self.player.grid(row=current_row, column=0, sticky='ew', pady=(0, 5))
        current_row += 1

        # 5. Gain Control Frame (gridded dynamically later)
        self.gain_frame = ttk.Frame(right_left_frame)
        self.gain_frame_grid_config = {'row': current_row, 'column': 0, 'sticky': 'ew', 'pady': 5}

        self.gain_label = ttk.Label(self.gain_frame, text="Volume Gain:")
        self.gain_label.pack(side=tk.LEFT, padx=5)
        self.gain_scale = ttk.Scale(self.gain_frame, from_=0.5, to=3.0, orient=tk.HORIZONTAL, variable=self.gain_var, command=lambda val: handlers.handle_gain_change(self, val))
        self.gain_scale.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.gain_value_label = ttk.Label(self.gain_frame, textvariable=self.gain_var, width=4)
        self.gain_var.trace_add("write", lambda *args: self._update_gain_label_format(*args))
        self.gain_value_label.pack(side=tk.LEFT, padx=5)

        # 6. Keyboard shortcuts hint
        self.shortcuts_label = ttk.Label(right_left_frame, text="Keyboard Shortcuts:")
        self.shortcuts_label.grid(row=current_row + 1, column=0, sticky='w', pady=(10,0))
        ttk.Label(right_left_frame, text="Ctrl+R: Redo  |  Esc: Stop Playback", foreground='gray50').grid(row=current_row + 2, column=0, sticky='w')
        ttk.Separator(right_left_frame, orient=tk.HORIZONTAL).grid(row=current_row + 3, column=0, sticky='ew', pady=(5,10))
        current_row += 4

        # 7. Progress bar (gridded dynamically later)
        self.progress_bar = ttk.Progressbar(right_left_frame, mode='indeterminate', variable=self.progress_var)
        self.progress_bar_grid_config = {'row': current_row, 'column': 0, 'sticky': 'ew', 'pady': 5}

        # 8. Bottom Button Frame
        bottom_button_frame = ttk.Frame(right_left_frame)
        bottom_button_frame.grid(row=100, column=0, sticky='sew', pady=10)
        right_left_frame.grid_rowconfigure(100, weight=0)
        bottom_button_frame.grid_columnconfigure(0, weight=1)

        self.save_btn = ttk.Button(bottom_button_frame, text="Save & Close", command=self.save_and_close)
        self.save_btn.grid(row=0, column=0, sticky='e', padx=5)

        self.finalize_btn = ttk.Button(bottom_button_frame, text="Generate Podcast", command=self.finalize)
        self.finalize_btn.grid(row=0, column=1, sticky='e', padx=5)

        # Final Setup
        self.language_var.set(LANGUAGES[0])
        handlers.update_voice_dropdown(self)
        widgets.clear_waveform(self)

    def _update_gain_label_format(self, *args):
        """Formats the gain value label to two decimal places."""
        try:
            value = self.gain_var.get()
            self.gain_value_label.config(text=f"{value:.2f}")
        except Exception:
            self.gain_value_label.config(text="-.--")

    def _prepare_final_data(self):
        """Gathers and structures the final segment details from the UI state."""
        self.final_structured_details = []
        for i in range(self.segment_listbox.size()):
            original_details = self.reviewable_segment_details.get(i)
            if original_details:
                details = original_details.copy()
                segment_type = details.get('type', 'speech')
                details['type'] = segment_type

                voice = details.get('voice')
                host_base_path = details.get('host_image')
                guest_base_path = details.get('guest_image')

                host_path_to_use = host_base_path
                guest_path_to_use = guest_base_path
                speaker_context = 'none'

                if segment_type == 'speech':
                    if voice == self.host_voice:
                        speaker_context = 'host_speaking'
                    elif voice == self.guest_voice:
                        speaker_context = 'guest_speaking'
                elif segment_type in ['intro', 'outro']:
                    speaker_context = 'intro_outro'

                print(f"  Finalizing Segment {i+1} ({segment_type}, Voice: {voice}, Context: {speaker_context})")

                if speaker_context == 'host_speaking':
                    host_path_to_use = widgets.find_corresponding_open_image(host_base_path)
                elif speaker_context == 'guest_speaking':
                    guest_path_to_use = widgets.find_corresponding_open_image(guest_base_path)

                details['host_image'] = host_path_to_use
                details['guest_image'] = guest_path_to_use
                self.final_structured_details.append(details)

    def save_and_close(self):
        """Saves progress and closes the window without finalizing."""
        print("TTSDevGUI: Save & Close clicked.")
        self.save_only = True
        self._prepare_final_data()
        if self.player:
            self.player.cleanup()
        self.root.quit()
        plt.close(self.fig)

    def finalize(self):
        """Finalizes the podcast and closes the window."""
        print("TTSDevGUI: Finalize clicked.")
        self.save_only = False
        self._prepare_final_data()
        if self.player:
            self.player.cleanup()
        self.root.quit()
        plt.close(self.fig)

    def run(self):
        """Runs the GUI main loop and returns the final data and save flag."""
        self.root.mainloop()
        print("TTSDevGUI: Mainloop finished.")
        final_structured_data = getattr(self, 'final_structured_details', None)
        save_only_flag = getattr(self, 'save_only', False)
        try:
            if self.player:
                self.player.cleanup()
            plt.close(self.fig)
            self.root.destroy()
            print("TTSDevGUI: Window destroyed.")
        except tk.TclError as e:
            print(f"TTSDevGUI: Error destroying window (maybe already destroyed): {e}")
        return final_structured_data, save_only_flag

    def populate_from_resumed_data(self, resumed_data):
        """Populates the GUI state from a loaded JSON object."""
        print("Populating GUI from resumed data...")
        # When resuming, all_segment_files is initially empty. We must rebuild it.
        self.all_segment_files = []

        for segment_data in resumed_data:
            segment_type = segment_data.get('type')
            audio_path = segment_data.get('audio_path')

            # Every segment, including silence, has an audio path that needs to be in all_segment_files
            # This path is what will be replaced on 'redo'
            self.all_segment_files.append(audio_path)
            current_original_index = len(self.all_segment_files) - 1

            if segment_type in ['intro', 'outro']:
                # Pass the correct original_index to the widget creation function
                widgets.add_special_segment(self, segment_type, data=segment_data, original_index=current_original_index)
            elif segment_type == 'speech':
                # Pass the correct original_index to the widget creation function
                widgets.add_reviewable_segment(self, current_original_index,
                                               segment_data.get('audio_path'),
                                               segment_data.get('text'),
                                               segment_data.get('voice'),
                                               padding_ms=segment_data.get('padding_ms', 0),
                                               data=segment_data)
            elif segment_type == 'silence':
                # Silence segments are not in the listbox, but are in all_segment_files.
                # The path was already added above. Nothing more to do here.
                pass
            else:
                print(f"  -> Skipping unknown segment type: {segment_type}")

        # After populating, select the first item to show its details
        if self.segment_listbox.size() > 0:
            self.segment_listbox.selection_set(0)
            handlers.on_segment_select(self, None)

def dev_mode_process(all_segment_files, reviewable_indices, text_segments_for_dev, api_host, api_port, speed, temp_dir, host_voice, guest_voice, resumed_data=None):
    """
    Handle development mode GUI review process.
    Can be initialized either from a new script or from resumed data.
    """
    try:
        import pygame
        pygame.mixer.init()
        if not pygame.mixer.get_init():
            messagebox.showerror("Error", "Pygame mixer failed to initialize. Cannot run Dev Mode GUI.")
            return None, False
    except ImportError:
        messagebox.showerror("Error", "Pygame library not found. Cannot run Dev Mode GUI.")
        return None, False

    print("Starting Dev Mode GUI...")
    gui = TTSDevGUI(api_host, api_port, speed, host_voice, guest_voice)
    gui.set_temp_dir(temp_dir)
    gui.set_all_segment_files(all_segment_files)

    if resumed_data:
        gui.populate_from_resumed_data(resumed_data)
    else:
        if not all_segment_files:
            print("Dev Mode: No segments (speech or silence) provided!")
            return all_segment_files, False
        if not reviewable_indices:
            print("Dev Mode: No reviewable speech segments found, skipping GUI.")
            return all_segment_files, False
        if len(reviewable_indices) != len(text_segments_for_dev):
            print(f"Dev Mode: Error - Mismatch between reviewable indices ({len(reviewable_indices)}) and text segment info ({len(text_segments_for_dev)}).")
            messagebox.showerror("Internal Error", "Mismatch in segment data for Dev Mode.")
            return None, False

        widgets.add_special_segment(gui, 'intro')
        speech_gui_start_index = gui.segment_listbox.size()
        for review_list_idx, original_idx in enumerate(reviewable_indices):
            if original_idx < len(all_segment_files) and review_list_idx < len(text_segments_for_dev):
                file_path = all_segment_files[original_idx]
                text, voice, padding_ms = text_segments_for__dev[review_list_idx]
                widgets.add_reviewable_segment(gui, original_idx, file_path, text, voice, padding_ms=padding_ms)
            else:
                print(f"Dev Mode: Warning - Index mismatch adding speech segment. Review Idx: {review_list_idx}, Original Idx: {original_idx}")
        widgets.add_special_segment(gui, 'outro')

    final_list, save_only = gui.run()
    return final_list, save_only