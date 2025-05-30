import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import os
import soundfile as sf
import pygame

# Constants (copied from orpheus_tts.py, consider centralizing if used elsewhere)
# SCRIPT_DIR = os.path.dirname(__file__) # This would be functions/tts/gui
# IMAGE_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", "settings/images"))
# MUSIC_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", "settings/music"))
# VOICE_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", "settings/voices"))

# Initialize pygame mixer (should ideally be done once at application start)
try:
    pygame.mixer.init()
    if not pygame.mixer.get_init():
        print("Warning: Pygame mixer failed to initialize.")
        pygame = None # Treat as if pygame is not available
except ImportError:
    print("Warning: 'pygame' library not found. pip install pygame")
    pygame = None

class AudioPlayer(ttk.Frame):
    def __init__(self, parent, redo_command=None, waveform_ax=None, waveform_canvas_agg=None):
        super().__init__(parent)
        self.redo_command = redo_command
        self.waveform_ax = waveform_ax
        self.waveform_canvas_agg = waveform_canvas_agg
        self.progress_line = None

        self.current_file = None
        self.is_playing = False
        self.current_pos = 0

        self.controls_frame = ttk.Frame(self)
        self.controls_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=(5, 2))

        self.play_btn = ttk.Button(self.controls_frame, text="Play", width=5, command=self.toggle_play, state=tk.DISABLED)
        self.play_btn.pack(side=tk.LEFT, padx=2)

        self.stop_btn = ttk.Button(self.controls_frame, text="Stop", width=5, command=self.stop, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=2)

        self.redo_btn = ttk.Button(self.controls_frame, text="Redo", width=5, command=self.redo_command, state=tk.DISABLED)
        self.redo_btn.pack(side=tk.LEFT, padx=2)

        self.progress_frame = ttk.Frame(self)
        self.progress_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=(0, 5))

        self.time_var = tk.StringVar(value="00:00 / 00:00")
        self.time_label = ttk.Label(self.progress_frame, textvariable=self.time_var)
        self.time_label.pack(side=tk.RIGHT, padx=5)

        self.update_thread = None

    def load_file(self, filepath):
        self.stop()
        self.current_file = None
        self.time_var.set("00:00 / 00:00")
        self.play_btn.configure(state=tk.DISABLED)
        self.stop_btn.configure(state=tk.DISABLED)
        self._update_progress_line(0)

        if not pygame:
            print("AudioPlayer: Pygame not available.")
            return False

        if not filepath:
            print("AudioPlayer: No file path provided.")
            return False

        print(f"AudioPlayer: Attempting to load audio file: {filepath}")
        if not os.path.exists(filepath):
             print(f"AudioPlayer: Error - File does not exist: {filepath}")
             return False

        try:
            info = sf.info(filepath)
            duration = info.frames / info.samplerate
            print(f"AudioPlayer: Duration calculated via soundfile: {duration:.2f}s")

            pygame.mixer.music.load(filepath)
            print(f"AudioPlayer: Pygame loaded: {filepath}")

            self.current_file = filepath
            self.duration = duration
            self.update_time_label(0, duration)
            self.play_btn.configure(state=tk.NORMAL)
            self.stop_btn.configure(state=tk.NORMAL)
            self._update_progress_line(0)
            return True

        except Exception as e:
            print(f"AudioPlayer: Error loading audio file {filepath}: {e}")
            self.current_file = None
            return False

    def toggle_play(self):
        if not self.current_file or not pygame or not pygame.mixer.get_init():
            return

        if self.is_playing:
            try:
                pygame.mixer.music.pause()
                self.play_btn.configure(text="Play")
                self.is_playing = False
            except Exception as e:
                 print(f"AudioPlayer: Error pausing music: {e}")
        else:
            try:
                if not pygame.mixer.music.get_busy():
                     print("AudioPlayer: Music not busy, reloading and playing from start/seek pos.")
                     pygame.mixer.music.load(self.current_file)
                     pygame.mixer.music.play(start=self.current_pos)
                else:
                     pygame.mixer.music.unpause()

                self.play_btn.configure(text="Pause")
                self.is_playing = True

                if not self.update_thread or not self.update_thread.is_alive():
                    self.update_thread = threading.Thread(target=self.update_progress, daemon=True)
                    self.update_thread.start()
            except Exception as e:
                messagebox.showerror("Playback Error", f"Error playing audio: {str(e)}")
                print(f"AudioPlayer: Error playing/unpausing music: {e}")
                self.is_playing = False
                self.play_btn.configure(text="Play")
                return

    def stop(self):
        if pygame and pygame.mixer.get_init():
            try:
                pygame.mixer.music.stop()
                pygame.mixer.music.unload()
            except Exception as e:
                print(f"AudioPlayer: Error stopping/unloading music: {e}")

        self.is_playing = False
        self.current_pos = 0
        self.play_btn.configure(text="Play")
        if self.current_file:
             self.play_btn.configure(state=tk.NORMAL)
        else:
             self.play_btn.configure(state=tk.DISABLED)
        self.update_time_label(0, getattr(self, 'duration', 0))
        self._update_progress_line(0)
        if self.current_file:
            self.stop_btn.configure(state=tk.NORMAL)
        else:
            self.stop_btn.configure(state=tk.DISABLED)

    def seek_to_time(self, target_time):
        """Seeks playback to the specified time (in seconds)."""
        if not self.current_file or not pygame or not pygame.mixer.get_init():
            return
        if target_time < 0 or target_time > self.duration:
            print(f"AudioPlayer: Invalid seek time: {target_time:.2f}s")
            return

        print(f"AudioPlayer: Seek requested to {target_time:.2f}s")
        was_playing = self.is_playing
        self.is_playing = False

        try:
            pygame.mixer.music.stop()
            pygame.mixer.music.load(self.current_file)
            pygame.mixer.music.play(start=target_time)
            self.current_pos = target_time
            self.is_playing = True
            self.play_btn.configure(text="Pause")
            self._update_progress_line(target_time)

            if not self.update_thread or not self.update_thread.is_alive():
                print("AudioPlayer: Restarting update thread after seek.")
                self.update_thread = threading.Thread(target=self.update_progress, daemon=True)
                self.update_thread.start()

        except Exception as e:
            print(f"AudioPlayer: Error seeking and playing: {e}")
            messagebox.showerror("Seek Error", f"Error seeking audio: {e}")
            self.stop()

    def update_progress(self):
        print("AudioPlayer: Starting update_progress loop.")
        while pygame and pygame.mixer.get_init() and self.current_file:
            if not self.is_playing:
                 print("AudioPlayer: is_playing is False, breaking loop.")
                 break
            try:
                current_playback_time = pygame.mixer.music.get_pos() / 1000.0
                display_pos = self.current_pos + current_playback_time

                if current_playback_time < 0:
                     if not pygame.mixer.music.get_busy():
                          print("AudioPlayer: Playback finished (get_busy is False).")
                          self.is_playing = False
                          self.play_btn.configure(text="Play")
                          self.current_pos = 0
                          print("AudioPlayer: Exiting loop after playback finished.")
                          break
                     else:
                          time.sleep(0.1)
                          continue

                if display_pos >= self.duration:
                    display_pos = self.duration
                    if not pygame.mixer.music.get_busy():
                        self.is_playing = False
                        self.play_btn.configure(text="Play")
                        self.current_pos = 0
                        self._update_progress_line(0)
                        self.update_time_label(0, self.duration)
                        print("AudioPlayer: Exiting loop after playback finished naturally.")
                        break

                self._update_progress_line(display_pos)
                self.update_time_label(display_pos, self.duration)

            except Exception as e:
                if isinstance(e, pygame.error) and "mixer not initialized" in str(e):
                     print("AudioPlayer: Mixer became uninitialized during update.")
                     self.is_playing = False
                     break
                print(f"AudioPlayer: Error in update_progress: {type(e).__name__} - {e}")
                self.is_playing = False
                break

            time.sleep(0.1)
        print("AudioPlayer: Exited update_progress loop.")

    def update_time_label(self, current, total):
         try:
            total = max(0, total)
            current = max(0, min(current, total))
            current_str = time.strftime("%M:%S", time.gmtime(current))
            total_str = time.strftime("%M:%S", time.gmtime(total))
            self.time_var.set(f"{current_str} / {total_str}")
         except ValueError as e:
            print(f"AudioPlayer: ValueError updating time label: {e}. Current: {current}, Total: {total}")
            self.time_var.set("--:-- / --:--")

    def _update_progress_line(self, time_pos):
        """Updates the vertical progress line on the waveform plot."""
        if self.waveform_ax and self.waveform_canvas_agg:
            try:
                xlim = self.waveform_ax.get_xlim()
                time_pos = max(xlim[0], min(time_pos, xlim[1]))
            except Exception:
                 pass

            if self.progress_line is None:
                if self.waveform_ax.lines:
                     self.progress_line = self.waveform_ax.axvline(time_pos, color='r', linestyle='--', linewidth=1, label='_nolegend_')
                else:
                     self.progress_line = None
                     return
            elif self.progress_line in self.waveform_ax.lines:
                self.progress_line.set_xdata([time_pos, time_pos])
            else:
                 self.progress_line = self.waveform_ax.axvline(time_pos, color='r', linestyle='--', linewidth=1, label='_nolegend_')

            try:
                self.waveform_canvas_agg.draw_idle()
            except Exception as e:
                print(f"AudioPlayer: Error drawing progress line: {e}")

    def cleanup(self):
        """Stop playback and cleanup resources"""
        print("AudioPlayer: Cleanup called.")
        self.is_playing = False
        self.stop()