import tkinter as tk
from tkinter import messagebox
import os
import threading
import time
import numpy as np
import soundfile as sf

# Import functions from other modules
from functions.tts.api import generate_audio_segment
from functions.tts.utils import load_voice_config
from functions.tts.args import LANGUAGES_VOICES, LANGUAGES # Import constants from args
from functions.tts.gui import widgets # Import widgets for helper functions

# Constants (re-defined for handlers, consider centralizing if truly global)
NO_MUSIC = "None"
NO_IMAGE = "None"

def on_segment_select(app_instance, event):
    print(f"DEBUG on_segment_select: Current details dict = {app_instance.reviewable_segment_details}")
    selection = app_instance.segment_listbox.curselection()
    if selection:
        gui_index = selection[0]
        if gui_index is None or gui_index < 0:
             print(f"TTSDevGUI: Invalid selection index ({gui_index}), skipping.")
             return
        app_instance.current_gui_selection = gui_index
        print(f"TTSDevGUI: Selected listbox index {app_instance.current_gui_selection}")

        details = app_instance.reviewable_segment_details.get(app_instance.current_gui_selection)
        app_instance.gui_index_to_original_index.get(app_instance.current_gui_selection) # Not directly used here, but kept for context

        print("DEBUG: Resetting UI elements...")
        app_instance.selected_segment_label.config(text="No Segment Selected")
        app_instance.text_display.config(state=tk.NORMAL)
        app_instance.text_display.delete(1.0, tk.END)
        app_instance.language_var.set(LANGUAGES[0])
        app_instance.voice_var.set("")
        update_voice_dropdown(app_instance)
        app_instance.bg_image_var.set("")
        app_instance.host_image_var.set("")
        app_instance.guest_image_var.set("")
        app_instance.intro_music_var.set("")
        app_instance.outro_music_var.set("")
        app_instance.gain_var.set(1.0)
        app_instance.ffmpeg_enhancement_var.set(True)
        app_instance.trim_end_ms_var.set(120)
        app_instance.nr_level_var.set(35)
        app_instance.compress_thresh_var.set(0.03)
        app_instance.compress_ratio_var.set(2)
        app_instance.norm_frame_len_var.set(20)
        app_instance.norm_gauss_size_var.set(15)
        app_instance.player.load_file(None)
        widgets.clear_waveform(app_instance)
        widgets._update_visual_preview(app_instance, speaker_context='none')
        _toggle_ffmpeg_params_visibility(app_instance)

        app_instance.text_display.config(state=tk.NORMAL)
        app_instance.language_combo.config(state='readonly')
        app_instance.voice_combo.config(state='readonly')
        if not app_instance.gain_frame.grid_info():
            app_instance.gain_frame.grid(**app_instance.gain_frame_grid_config)
        if app_instance.player: app_instance.player.redo_btn.configure(state=tk.DISABLED)
        app_instance.intro_music_combo.config(state=tk.DISABLED)
        app_instance.outro_music_combo.config(state=tk.DISABLED)
        app_instance.bg_combo.config(state='readonly' if app_instance.background_names else tk.DISABLED)
        host_images_exist = len(app_instance.host_open_image_files) > 1 or len(app_instance.host_closed_image_files) > 1
        guest_images_exist = len(app_instance.guest_open_image_files) > 1 or len(app_instance.guest_closed_image_files) > 1
        app_instance.host_img_combo.config(state='readonly' if host_images_exist else tk.DISABLED)
        app_instance.guest_img_combo.config(state='readonly' if guest_images_exist else tk.DISABLED)

        try:
            selected_name = app_instance.segment_listbox.get(gui_index)
            app_instance.selected_segment_label.config(text=f"Selected: {selected_name}")
        except tk.TclError:
             app_instance.selected_segment_label.config(text="Error getting segment name")

        print("DEBUG: Checking details...")
        if details:
            segment_type = details.get('type', 'speech')
            print(f"DEBUG: Segment type: {segment_type}")

            print("DEBUG: Populating text display...")
            text_to_insert = details.get('text', '[No Text]')
            print(f"DEBUG: Text content to insert: {repr(text_to_insert)}")

            print("DEBUG: Populating BG image dropdown var...")
            bg_base_path = details.get('bg_image') or NO_IMAGE
            app_instance.bg_image_var.set(os.path.basename(bg_base_path) if bg_base_path != NO_IMAGE else NO_IMAGE)

            speaker_context = 'none'
            voice = details.get('voice')
            if segment_type == 'speech':
                if voice == app_instance.host_voice:
                    speaker_context = 'host_speaking'
                elif voice == app_instance.guest_voice:
                    speaker_context = 'guest_speaking'
            elif segment_type in ['intro', 'outro']:
                speaker_context = 'intro_outro'
            print(f"DEBUG: Speaker context determined: {speaker_context}")

            host_base_path = details.get('host_image') or NO_IMAGE
            guest_base_path = details.get('guest_image') or NO_IMAGE

            host_names_to_show = app_instance.host_closed_image_names
            guest_names_to_show = app_instance.guest_closed_image_names
            host_path_to_select = host_base_path
            guest_path_to_select = guest_base_path

            def find_corresponding_open_image_for_select(base_path):
                print(f"DEBUG (select) find_corresponding_open_image: Called with base_path='{base_path}'")
                if not base_path or base_path == NO_IMAGE or not os.path.exists(base_path): return base_path
                try:
                    closed_dir = os.path.dirname(base_path)
                    if os.path.basename(closed_dir) != 'closed': return base_path
                    parent_dir = os.path.dirname(closed_dir)
                    open_dir = os.path.join(parent_dir, 'open')
                    if not os.path.isdir(open_dir): return base_path

                    image_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp')
                    all_open_images = []
                    for f in os.listdir(open_dir):
                        if os.path.isfile(os.path.join(open_dir, f)) and f.lower().endswith(image_extensions):
                            all_open_images.append(f)
                    if all_open_images:
                        open_image_path = os.path.join(open_dir, all_open_images[0])
                        print(f"    -> (select) Found open image: {os.path.basename(open_image_path)}")
                        return open_image_path
                    else:
                        return base_path
                except Exception as e:
                     print(f"    -> (select) Error finding open image: {e}. Returning closed path.")
                     return base_path

            if speaker_context == 'host_speaking':
                host_names_to_show = app_instance.host_open_image_names
                host_path_to_select = find_corresponding_open_image_for_select(host_base_path)
                guest_names_to_show = app_instance.guest_closed_image_names
                guest_path_to_select = guest_base_path
            elif speaker_context == 'guest_speaking':
                host_names_to_show = app_instance.host_closed_image_names
                host_path_to_select = host_base_path
                guest_names_to_show = app_instance.guest_open_image_names
                guest_path_to_select = find_corresponding_open_image_for_select(guest_base_path)

            host_name_to_select = os.path.basename(host_path_to_select) if host_path_to_select != NO_IMAGE else NO_IMAGE
            guest_name_to_select = os.path.basename(guest_path_to_select) if guest_path_to_select != NO_IMAGE else NO_IMAGE

            print(f"DEBUG: Host Dropdown: Values={host_names_to_show}, Select='{host_name_to_select}'")
            print(f"DEBUG: Guest Dropdown: Values={guest_names_to_show}, Select='{guest_name_to_select}'")

            app_instance.host_img_combo['values'] = host_names_to_show
            app_instance.guest_img_combo['values'] = guest_names_to_show

            app_instance.host_image_var.set(host_name_to_select)
            app_instance.guest_image_var.set(guest_name_to_select)

            print("DEBUG: Updating visual preview with context...")
            widgets._update_visual_preview(app_instance, bg_path=bg_base_path, host_base_path=host_base_path, guest_base_path=guest_base_path, speaker_context=speaker_context)

            audio_path_to_load = details.get('audio_path')

            if segment_type == 'speech':
                print("DEBUG: Configuring UI for SPEECH segment...")
                app_instance.text_display.config(state=tk.NORMAL)
                app_instance.text_display.delete(1.0, tk.END)
                app_instance.text_display.insert(tk.END, details.get('text', ''))
                print(f"DEBUG: Text display populated with: {details.get('text', '')[:50]}...")

                current_voice = details.get('voice', '')
                current_language = LANGUAGES[0]
                for lang, voices in LANGUAGES_VOICES.items():
                    if current_voice in voices:
                        current_language = lang
                        break
                app_instance.language_var.set(current_language)
                update_voice_dropdown(app_instance)
                app_instance.voice_var.set(current_voice)

                app_instance.gain_var.set(details.get('gain', 1.0))
                app_instance._update_gain_label_format()

                # Load settings from the details dict if they exist, otherwise load from voice config
                print(f"  Segment {app_instance.current_gui_selection}: Loading UI settings for voice '{voice}'.")
                voice_config = load_voice_config(voice)

                # Get gain, falling back from details -> voice_config -> default
                gain = details.get('gain', voice_config.get('gain_factor', 1.0))
                
                # Get trim, falling back from details -> voice_config -> default
                trim_end_ms = details.get('trim_end_ms', voice_config.get('trim_end_ms', 120))

                # Get padding from details. If it's None or 0, recalculate it based on defaults.
                padding_ms = details.get('padding_ms')
                if padding_ms is None or padding_ms == 0: # Force recalculation if None or explicitly 0
                    next_gui_index = app_instance.current_gui_selection + 1
                    if next_gui_index < app_instance.segment_listbox.size():
                        next_details = app_instance.reviewable_segment_details.get(next_gui_index)
                        if next_details:
                            next_segment_type = next_details.get('type')
                            if next_segment_type == 'speech':
                                # Determine padding based on speaker change or same speaker
                                padding_ms = 100 if voice == next_details.get('voice') else 750
                            else: # Next is intro/outro
                                padding_ms = 750
                        else:
                            padding_ms = 0 # No next details found, so no padding
                    else: # Last segment, no padding needed
                        padding_ms = 0
                    print(f"  Segment {app_instance.current_gui_selection}: Calculated padding: {padding_ms}ms")
                    # Update the details dictionary with the newly calculated padding
                    details['padding_ms'] = padding_ms
                else:
                    print(f"  Segment {app_instance.current_gui_selection}: Loaded padding from details: {padding_ms}ms")

                # Set padding_ms_var here after calculation/loading
                app_instance.padding_ms_var.set(padding_ms)

                # Get FFmpeg/De-esser settings from details, falling back to voice config/defaults
                ffmpeg_enabled = details.get('apply_ffmpeg_enhancement', voice != 'leo')
                deesser_enabled = details.get('apply_deesser', voice != 'leo')
                nr_level = details.get('nr_level', voice_config.get('nr_level', 35))
                compress_thresh = details.get('compress_thresh', voice_config.get('compress_thresh', 0.03))
                compress_ratio = details.get('compress_ratio', voice_config.get('compress_ratio', 2))
                norm_frame_len = details.get('norm_frame_len', voice_config.get('norm_frame_len', 20))
                norm_gauss_size = details.get('norm_gauss_size', voice_config.get('norm_gauss_size', 15))
                deesser_freq = details.get('deesser_freq', voice_config.get('deesser_freq', 5000))

                if norm_gauss_size % 2 == 0:
                    norm_gauss_size -= 1

                # Set all the UI variables from the determined values
                app_instance.ffmpeg_enhancement_var.set(ffmpeg_enabled)
                app_instance.deesser_var.set(deesser_enabled)
                app_instance.gain_var.set(gain)
                app_instance.trim_end_ms_var.set(trim_end_ms)
                app_instance.deesser_freq_var.set(deesser_freq)
                app_instance.nr_level_var.set(nr_level)
                app_instance.compress_thresh_var.set(compress_thresh)
                app_instance.compress_ratio_var.set(compress_ratio)
                app_instance.norm_frame_len_var.set(norm_frame_len)
                app_instance.norm_gauss_size_var.set(norm_gauss_size)

                app_instance.deesser_freq_spinbox.configure(state='normal' if (ffmpeg_enabled and deesser_enabled) else 'disabled')

                _toggle_ffmpeg_params_visibility(app_instance)
                app_instance.intro_music_combo.config(state=tk.DISABLED)
                app_instance.outro_music_combo.config(state=tk.DISABLED)
                app_instance.text_display.config(state=tk.NORMAL)
                app_instance.language_combo.config(state='readonly')
                app_instance.voice_combo.config(state='readonly')
                if not app_instance.gain_frame.grid_info():
                    app_instance.gain_frame.grid(**app_instance.gain_frame_grid_config)
                
                # Ensure padding spinbox is enabled for speech segments
                app_instance.padding_spinbox.config(state=tk.NORMAL)

            elif segment_type in ['intro', 'outro']:
                print(f"DEBUG: Configuring UI for {segment_type.upper()} segment...")
                music_path = details.get('audio_path', NO_MUSIC)
                music_var = app_instance.intro_music_var if segment_type == 'intro' else app_instance.outro_music_var
                music_combo = app_instance.intro_music_combo if segment_type == 'intro' else app_instance.outro_music_combo
                
                music_var.set(os.path.basename(music_path) if music_path != NO_MUSIC else NO_MUSIC)
                audio_path_to_load = music_path
                
                # Disable all speech-related controls, including padding
                app_instance.text_display.config(state=tk.DISABLED)
                app_instance.language_combo.config(state=tk.DISABLED)
                app_instance.voice_combo.config(state=tk.DISABLED)
                app_instance.padding_spinbox.config(state=tk.DISABLED) # Disable padding for intro/outro
                if app_instance.gain_frame.grid_info(): app_instance.gain_frame.grid_forget()
                if app_instance.player: app_instance.player.redo_btn.configure(state=tk.DISABLED)
                
                # Enable the correct music combo, disable the other
                app_instance.intro_music_combo.config(state=tk.DISABLED)
                app_instance.outro_music_combo.config(state=tk.DISABLED)
                music_combo.config(state='readonly' if widgets.pydub_available and music_combo['values'] else tk.DISABLED)

            print(f"DEBUG: Preparing to load audio file: {audio_path_to_load}")
            # Always enable redo button for speech segments, regardless of audio file existence
            if segment_type == 'speech' and app_instance.player:
                app_instance.player.redo_btn.configure(state=tk.NORMAL)

            if audio_path_to_load and audio_path_to_load not in [NO_MUSIC, NO_IMAGE]:
                print(f"DEBUG: Attempting to load audio file path: {audio_path_to_load}")
                if not os.path.exists(audio_path_to_load):
                    print(f"ERROR - File does not exist: {audio_path_to_load}")
                    messagebox.showerror("Load Error", f"Audio file not found:\n{audio_path_to_load}")
                    widgets.clear_waveform(app_instance) # Clear waveform if file not found
                    app_instance.player.load_file(None) # Ensure player is cleared
                else:
                    print(f"DEBUG: Calling app_instance.player.load_file({audio_path_to_load})...")
                    if app_instance.player.load_file(audio_path_to_load):
                        print("DEBUG: Audio file loaded successfully.")
                        print("DEBUG: Updating waveform...")
                        widgets.update_waveform(app_instance, audio_path_to_load)
                        print("DEBUG: Waveform updated.")
                    else:
                         messagebox.showerror("Load Error", f"Failed to load audio file:\n{audio_path_to_load}")
                         widgets.clear_waveform(app_instance) # Clear waveform if load fails
            else:
                print("DEBUG: No valid audio path to load.")
                widgets.clear_waveform(app_instance)

        else:
             print(f"TTSDevGUI: Error - Could not find details for GUI index {app_instance.current_gui_selection}")

def update_voice_dropdown(app_instance):
    """Updates the voice combobox based on the selected language."""
    selected_language = app_instance.language_var.get()
    voices = LANGUAGES_VOICES.get(selected_language, [])
    app_instance.voice_combo['values'] = voices
    if voices:
        current_voice = app_instance.voice_var.get()
        if current_voice not in voices:
            app_instance.voice_var.set(voices[0])
    else:
        app_instance.voice_var.set('')
    print(f"Updated voice dropdown for language '{selected_language}': {voices}")

def handle_language_change(app_instance, event=None):
    """Handle language selection change."""
    update_voice_dropdown(app_instance)

def handle_voice_change(app_instance, event=None):
    """Handle voice selection changes and optionally regenerate audio"""
    if app_instance.current_gui_selection is not None:
        details = app_instance.reviewable_segment_details.get(app_instance.current_gui_selection)
        if details:
            new_voice = app_instance.voice_var.get()
            if new_voice != details['voice']:
                details['voice'] = new_voice
                widgets.update_segment_display_name(app_instance, app_instance.current_gui_selection)
                if messagebox.askyesno("Voice Changed", "Would you like to regenerate the segment with the new voice?"):
                    redo_segment(app_instance)

def handle_bg_change(app_instance, event=None):
    """Handle background image selection change."""
    print("DEBUG: handle_bg_change triggered")
    if app_instance.current_gui_selection is not None:
        print(f"DEBUG handle_bg_change: Modifying index {app_instance.current_gui_selection}")
        details = app_instance.reviewable_segment_details.get(app_instance.current_gui_selection)
        print(f"DEBUG handle_bg_change: Details before change = {details}")
        if details:
            selected_name = app_instance.bg_image_var.get()
            selected_base_path = app_instance.name_to_path.get(selected_name)
            details['bg_image'] = selected_base_path
            speaker_context = getattr(app_instance, '_current_preview_context', 'none')
            widgets._update_visual_preview(
                app_instance,
                bg_path=details.get('bg_image'),
                host_base_path=details.get('host_image'),
                guest_base_path=details.get('guest_image'),
                speaker_context=speaker_context
            )
            print(f"Segment {app_instance.current_gui_selection}: Background changed to {selected_name}")

def _get_corresponding_closed_path(app_instance, current_path):
    """Given a path (potentially in 'open'), find the corresponding path in 'closed'."""
    if not current_path or current_path == NO_IMAGE or not os.path.exists(current_path):
        return current_path

    try:
        current_dir = os.path.dirname(current_path)
        current_filename = os.path.basename(current_path)

        if os.path.basename(current_dir) == 'closed':
            return current_path

        if os.path.basename(current_dir) == 'open':
            parent_dir = os.path.dirname(current_dir)
            closed_dir = os.path.join(parent_dir, 'closed')
            if os.path.isdir(closed_dir):
                image_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp')
                closed_images = sorted([
                    os.path.join(closed_dir, f)
                    for f in os.listdir(closed_dir)
                    if os.path.isfile(os.path.join(closed_dir, f)) and f.lower().endswith(image_extensions)
                ])
                if closed_images:
                    print(f"DEBUG _get_corresponding_closed_path: Found closed path {os.path.basename(closed_images[0])} for open path {current_filename}")
                    return closed_images[0]
                else:
                     print(f"DEBUG _get_corresponding_closed_path: No images found in corresponding closed dir '{closed_dir}' for {current_filename}")
            else:
                 print(f"DEBUG _get_corresponding_closed_path: Corresponding closed dir '{closed_dir}' not found for {current_filename}")

        print(f"DEBUG _get_corresponding_closed_path: Could not determine closed path for {current_filename}. Returning original.")
        return current_path
    except Exception as e:
        print(f"DEBUG _get_corresponding_closed_path: Error processing {current_path}: {e}. Returning original.")
        return current_path

def handle_host_img_change(app_instance, event=None):
    """Handle host image selection change."""
    print("DEBUG: handle_host_img_change triggered")
    if app_instance.current_gui_selection is not None:
        details = app_instance.reviewable_segment_details.get(app_instance.current_gui_selection)
        if details:
            selected_name = app_instance.host_image_var.get()
            selected_path = app_instance.name_to_path.get(selected_name)

            closed_path_to_store = _get_corresponding_closed_path(app_instance, selected_path)
            print(f"DEBUG handle_host_img_change: Selected path='{selected_path}', Closed path to store='{closed_path_to_store}'")

            details['host_image'] = closed_path_to_store

            speaker_context = getattr(app_instance, '_current_preview_context', 'none')
            widgets._update_visual_preview(
                app_instance,
                bg_path=details.get('bg_image'),
                host_base_path=details.get('host_image'),
                guest_base_path=details.get('guest_image'),
                speaker_context=speaker_context
            )
            print(f"Segment {app_instance.current_gui_selection}: Host image changed to {selected_name} (Stored base: {os.path.basename(closed_path_to_store)})")

def handle_guest_img_change(app_instance, event=None):
    """Handle guest image selection change."""
    print("DEBUG: handle_guest_img_change triggered")
    if app_instance.current_gui_selection is not None:
        details = app_instance.reviewable_segment_details.get(app_instance.current_gui_selection)
        if details:
            selected_name = app_instance.guest_image_var.get()
            selected_path = app_instance.name_to_path.get(selected_name)

            closed_path_to_store = _get_corresponding_closed_path(app_instance, selected_path)
            print(f"DEBUG handle_guest_img_change: Selected path='{selected_path}', Closed path to store='{closed_path_to_store}'")

            details['guest_image'] = closed_path_to_store

            speaker_context = getattr(app_instance, '_current_preview_context', 'none')
            widgets._update_visual_preview(
                app_instance,
                bg_path=details.get('bg_image'),
                host_base_path=details.get('host_image'),
                guest_base_path=details.get('guest_image'),
                speaker_context=speaker_context
            )
            print(f"Segment {app_instance.current_gui_selection}: Guest image changed to {selected_name} (Stored base: {os.path.basename(closed_path_to_store)})")

def handle_intro_music_change(app_instance, event=None):
    """Handle intro music selection change."""
    print("DEBUG: handle_intro_music_change triggered")
    if app_instance.current_gui_selection is not None:
        print(f"DEBUG handle_intro_music_change: Modifying index {app_instance.current_gui_selection}")
        details = app_instance.reviewable_segment_details.get(app_instance.current_gui_selection)
        print(f"DEBUG handle_intro_music_change: Details before change = {details}")
        if details:
            selected_name = app_instance.intro_music_var.get()
            selected_path = app_instance.name_to_path.get(selected_name)
            details['intro_music'] = selected_path
            print(f"Segment {app_instance.current_gui_selection}: Intro music changed to {selected_name}")

def handle_outro_music_change(app_instance, event=None):
    """Handle outro music selection change."""
    print("DEBUG: handle_outro_music_change triggered")
    if app_instance.current_gui_selection is not None:
        print(f"DEBUG handle_outro_music_change: Modifying index {app_instance.current_gui_selection}")
        details = app_instance.reviewable_segment_details.get(app_instance.current_gui_selection)
        print(f"DEBUG handle_outro_music_change: Details before change = {details}")
        if details and details.get('type') == 'outro':
            selected_name = app_instance.outro_music_var.get()
            selected_path = app_instance.name_to_path.get(selected_name)
            details['outro_music'] = selected_path
            details['audio_path'] = selected_path
            print(f"Segment {app_instance.current_gui_selection} (Outro): Music changed to {selected_name}")
            if selected_path and selected_path != NO_MUSIC and os.path.exists(selected_path):
                if app_instance.player.load_file(selected_path):
                    widgets.update_waveform(app_instance, selected_path)
                else:
                    messagebox.showerror("Load Error", f"Failed to load selected outro music:\n{selected_path}")
                    widgets.clear_waveform(app_instance)
            else:
                app_instance.player.load_file(None)
                widgets.clear_waveform(app_instance)

def handle_ffmpeg_change(app_instance):
    """Update stored FFmpeg setting when Checkbutton is toggled."""
    if app_instance.current_gui_selection is not None:
        details = app_instance.reviewable_segment_details.get(app_instance.current_gui_selection)
        if details and details.get('type') == 'speech':
            new_state = app_instance.ffmpeg_enhancement_var.get()
            details['apply_ffmpeg_enhancement'] = new_state
            deesser_enabled = app_instance.deesser_var.get() if new_state else False
            details['apply_deesser'] = deesser_enabled
            print(f"Segment {app_instance.current_gui_selection}: FFmpeg Enhancement set to {new_state}")
            print(f"Segment {app_instance.current_gui_selection}: De-esser set to {deesser_enabled}")
            
            app_instance.deesser_freq_spinbox.configure(state='normal' if (new_state and deesser_enabled) else 'disabled')
            
            _toggle_ffmpeg_params_visibility(app_instance)

def handle_deesser_change(app_instance):
    """Handle changes to the de-esser checkbox."""
    if app_instance.current_gui_selection is not None:
        details = app_instance.reviewable_segment_details.get(app_instance.current_gui_selection)
        if details and details.get('type') == 'speech':
            deesser_enabled = app_instance.deesser_var.get()
            details['apply_deesser'] = deesser_enabled
            ffmpeg_enabled = app_instance.ffmpeg_enhancement_var.get()
            app_instance.deesser_freq_spinbox.configure(state='normal' if (ffmpeg_enabled and deesser_enabled) else 'disabled')
            print(f"Segment {app_instance.current_gui_selection}: De-esser set to {deesser_enabled}")

def _toggle_ffmpeg_params_visibility(app_instance):
    """Shows or hides the FFmpeg parameter controls based on the main checkbox."""
    try:
        if app_instance.ffmpeg_enhancement_var.get():
            if not app_instance.ffmpeg_params_frame.grid_info():
                app_instance.ffmpeg_params_frame.grid(**app_instance.ffmpeg_params_frame_grid_config)
        else:
            if app_instance.ffmpeg_params_frame.grid_info():
                app_instance.ffmpeg_params_frame.grid_forget()
    except tk.TclError as e:
         print(f"Warning: TclError toggling FFmpeg params visibility (widget might not exist yet): {e}")

def handle_trim_change(app_instance):
    """Update stored trim value when Spinbox command is triggered (arrow keys/direct click)."""
    if app_instance.current_gui_selection is not None:
        details = app_instance.reviewable_segment_details.get(app_instance.current_gui_selection)
        if details and details.get('type') == 'speech':
            try:
                new_trim = app_instance.trim_end_ms_var.get()
                if new_trim >= 0:
                   details['trim_end_ms'] = new_trim
                   print(f"Segment {app_instance.current_gui_selection}: Trim End set to {new_trim}ms")
                else:
                   print(f"Segment {app_instance.current_gui_selection}: Invalid trim value entered ({new_trim}). Ignoring.")
                   app_instance.trim_end_ms_var.set(details.get('trim_end_ms', 120))
            except tk.TclError:
                print(f"Segment {app_instance.current_gui_selection}: Invalid trim value entered. Ignoring.")
                app_instance.trim_end_ms_var.set(details.get('trim_end_ms', 120))

def handle_trim_change_trace(app_instance, *args):
    """Update stored trim value when the trim_end_ms_var changes (e.g., direct text input)."""
    if app_instance.current_gui_selection is not None:
        details = app_instance.reviewable_segment_details.get(app_instance.current_gui_selection)
        if details and details.get('type') == 'speech':
            try:
                new_trim = app_instance.trim_end_ms_var.get()
                if new_trim >= 0:
                   if details.get('trim_end_ms') != new_trim:
                       details['trim_end_ms'] = new_trim
                       print(f"Segment {app_instance.current_gui_selection} (Trace): Trim End set to {new_trim}ms")
            except tk.TclError:
                pass

def handle_padding_change(app_instance):
    """Update stored padding value when Spinbox command is triggered (arrow keys/direct click)."""
    if app_instance.current_gui_selection is not None:
        details = app_instance.reviewable_segment_details.get(app_instance.current_gui_selection)
        if details and details.get('type') == 'speech':
            try:
                new_padding = app_instance.padding_ms_var.get()
                if new_padding >= 0:
                   details['padding_ms'] = new_padding
                   print(f"Segment {app_instance.current_gui_selection}: Padding set to {new_padding}ms")
                else:
                   print(f"Segment {app_instance.current_gui_selection}: Invalid padding value entered ({new_padding}). Ignoring.")
                   app_instance.padding_ms_var.set(details.get('padding_ms', 0))
            except tk.TclError:
                print(f"Segment {app_instance.current_gui_selection}: Invalid padding value entered. Ignoring.")
                app_instance.padding_ms_var.set(details.get('padding_ms', 0))

def handle_padding_change_trace(app_instance, *args):
    """Update stored padding value when the padding_ms_var changes (e.g., direct text input)."""
    if app_instance.current_gui_selection is not None:
        details = app_instance.reviewable_segment_details.get(app_instance.current_gui_selection)
        if details and details.get('type') == 'speech':
            try:
                new_padding = app_instance.padding_ms_var.get()
                if new_padding >= 0:
                   if details.get('padding_ms') != new_padding:
                       details['padding_ms'] = new_padding
                       print(f"Segment {app_instance.current_gui_selection} (Trace): Padding set to {new_padding}ms")
            except tk.TclError:
                pass

def handle_ffmpeg_param_change(app_instance):
    """Generic handler for Spinbox command changes for FFmpeg params."""
    _update_ffmpeg_details_from_vars(app_instance)

def handle_ffmpeg_param_change_trace(app_instance, *args):
    """Generic handler for variable traces for FFmpeg params."""
    _update_ffmpeg_details_from_vars(app_instance)

def _update_ffmpeg_details_from_vars(app_instance):
    """Reads FFmpeg parameter variables and updates the details dictionary."""
    if app_instance.current_gui_selection is None: return
    details = app_instance.reviewable_segment_details.get(app_instance.current_gui_selection)
    if not details or details.get('type') != 'speech': return

    updated = False
    try:
        nr_level = app_instance.nr_level_var.get()
        if nr_level >= 0 and nr_level <= 97 and details.get('nr_level') != nr_level:
            details['nr_level'] = nr_level
            print(f"Segment {app_instance.current_gui_selection}: NR Level set to {nr_level}")
            updated = True

        try:
            comp_thresh = app_instance.compress_thresh_var.get()
            if comp_thresh >= 0.001 and comp_thresh <= 1.0 and details.get('compress_thresh') != comp_thresh:
                 details['compress_thresh'] = comp_thresh
                 print(f"Segment {app_instance.current_gui_selection}: Comp Threshold set to {comp_thresh:.3f}")
                 updated = True
            elif comp_thresh < 0.001 or comp_thresh > 1.0:
                 print(f"Segment {app_instance.current_gui_selection}: Invalid Comp Threshold ({comp_thresh:.3f}). Clamping or reverting might be needed.")
        except tk.TclError:
            print(f"Segment {app_instance.current_gui_selection}: Invalid Comp Threshold input.")

        comp_ratio = app_instance.compress_ratio_var.get()
        if comp_ratio >= 1 and comp_ratio <= 20 and details.get('compress_ratio') != comp_ratio:
            details['compress_ratio'] = comp_ratio
            print(f"Segment {app_instance.current_gui_selection}: Comp Ratio set to {comp_ratio}")
            updated = True

        norm_f = app_instance.norm_frame_len_var.get()
        if norm_f >= 10 and norm_f <= 8000 and details.get('norm_frame_len') != norm_f:
            details['norm_frame_len'] = norm_f
            print(f"Segment {app_instance.current_gui_selection}: Norm Frame set to {norm_f}")
            updated = True

        norm_g = app_instance.norm_gauss_size_var.get()
        if norm_g >= 3 and norm_g <= 301:
            if norm_g % 2 == 0:
                norm_g -= 1
                app_instance.norm_gauss_size_var.set(norm_g)
            if details.get('norm_gauss_size') != norm_g:
                details['norm_gauss_size'] = norm_g
                print(f"Segment {app_instance.current_gui_selection}: Norm Gauss set to {norm_g}")
                updated = True
        elif norm_g < 3:
             app_instance.norm_gauss_size_var.set(3)
             if details.get('norm_gauss_size') != 3:
                details['norm_gauss_size'] = 3
                print(f"Segment {app_instance.current_gui_selection}: Norm Gauss set to {3}")
                updated = True

    except tk.TclError:
        pass

def on_waveform_click(app_instance, event):
    """Handle clicks on the waveform plot for seeking."""
    if event.inaxes != app_instance.ax or not app_instance.player or not app_instance.player.current_file or not hasattr(app_instance.player, 'duration'):
        return

    clicked_time = event.xdata
    if clicked_time is not None and clicked_time >= 0 and clicked_time <= app_instance.player.duration:
        print(f"TTSDevGUI: Waveform clicked at time {clicked_time:.2f}s")
        app_instance.player.seek_to_time(clicked_time)
    else:
         print(f"TTSDevGUI: Waveform click ignored (time={clicked_time})")

def handle_gain_change(app_instance, value_str):
    """Update the stored gain value when the scale is moved for any selected segment."""
    if app_instance.current_gui_selection is not None:
        details = app_instance.reviewable_segment_details.get(app_instance.current_gui_selection)
        if details:
            try:
                new_gain = float(value_str)
                details['gain'] = new_gain
            except ValueError:
                print("TTSDevGUI: Invalid gain value from scale.")

def redo_segment(app_instance):
    if app_instance.current_gui_selection is None or app_instance.temp_dir is None:
         messagebox.showwarning("Cannot Redo", "Please select a segment from the list first.")
         return

    details = app_instance.reviewable_segment_details.get(app_instance.current_gui_selection)
    original_index = app_instance.gui_index_to_original_index.get(app_instance.current_gui_selection)

    if not details or original_index is None:
         messagebox.showerror("Error", f"Could not find details for selected segment.")
         return

    if original_index >= len(app_instance.all_segment_files):
         messagebox.showerror("Error", f"Internal error: Original index out of bounds.")
         return

    old_file_path = app_instance.all_segment_files[original_index]
    text = app_instance.text_display.get(1.0, tk.END).strip()

    if not text:
        messagebox.showerror("Error", "Text cannot be empty.")
        return

    details['text'] = text
    voice = app_instance.voice_var.get()
    details['voice'] = voice

    gain_to_apply = details.get('gain', 1.0)
    padding_to_apply = details.get('padding_ms', 0)
    apply_ffmpeg = details.get('apply_ffmpeg_enhancement', True)
    nr_level = details.get('nr_level', 35)
    compress_thresh = details.get('compress_thresh', 0.03)
    compress_ratio = details.get('compress_ratio', 2)
    norm_frame_len = details.get('norm_frame_len', 20)
    norm_gauss_size = details.get('norm_gauss_size', 15)

    apply_deesser = details.get('apply_deesser', True)
    deesser_freq = details.get('deesser_freq', 5000)
    
    print(f"TTSDevGUI: Redoing segment (Original Index {original_index}, GUI Index {app_instance.current_gui_selection}, Voice: {voice}, Gain: {gain_to_apply:.2f}, Padding: {padding_to_apply}ms)")
    if apply_ffmpeg:
        print(f"  -> FFmpeg Params: NR={nr_level}, CompThresh={compress_thresh:.3f}, CompRatio={compress_ratio}, NormFrame={norm_frame_len}, NormGauss={norm_gauss_size}")
        if apply_deesser:
            print(f"  -> De-esser: Enabled (Freq: {deesser_freq} Hz)")
        else:
            print("  -> De-esser: Disabled")
    else:
        print("  -> FFmpeg Enhancement: Disabled (including De-esser)")
    print(f"  -> Old File: {old_file_path}")

    app_instance.player.stop()

    app_instance.progress_bar.grid(**app_instance.progress_bar_grid_config)
    app_instance.progress_bar.start(10)
    if app_instance.player: app_instance.player.redo_btn.configure(state=tk.DISABLED)
    app_instance.root.config(cursor="watch")
    app_instance.root.update_idletasks()

    thread = threading.Thread(target=_thread_generate_audio,
                               args=(app_instance, text, voice, original_index, old_file_path, gain_to_apply, padding_to_apply,
                                     apply_ffmpeg, nr_level, compress_thresh, compress_ratio, norm_frame_len, norm_gauss_size),
                              daemon=True)
    thread.start()

def _thread_generate_audio(app_instance, text, voice, original_index, old_file_path, gain_factor, padding_ms,
                            apply_ffmpeg, nr_level, compress_thresh, compress_ratio, norm_frame_len, norm_gauss_size):
    """Runs audio generation in a background thread with FFmpeg parameters."""
    details = app_instance.reviewable_segment_details.get(app_instance.current_gui_selection, {})
    apply_deesser = details.get('apply_deesser', True)
    deesser_freq = details.get('deesser_freq', 5000)
    
    new_file_path, new_sr = generate_audio_segment(
        text, voice, app_instance.speed, app_instance.api_host, app_instance.api_port, app_instance.temp_dir,
        gain_factor=gain_factor,
        pad_end_ms=padding_ms,
        apply_ffmpeg_enhancement=apply_ffmpeg,
        apply_deesser=apply_deesser,
        deesser_freq=deesser_freq,
        nr_level=nr_level,
        compress_thresh=compress_thresh,
        compress_ratio=compress_ratio,
        norm_frame_len=norm_frame_len,
        norm_gauss_size=norm_gauss_size
    )
    app_instance.root.after(0, _finish_redo_ui, app_instance, new_file_path, original_index, old_file_path)

def _finish_redo_ui(app_instance, new_file_path, original_index, old_file_path):
    """Updates the UI after audio generation thread finishes."""
    app_instance.progress_bar.stop()
    if app_instance.progress_bar.grid_info():
        app_instance.progress_bar.grid_forget()
    app_instance.root.config(cursor="")
    if app_instance.player: app_instance.player.redo_btn.configure(state=tk.NORMAL)

    if new_file_path:
        print(f"TTSDevGUI: Segment regenerated successfully: {new_file_path}")
        app_instance.all_segment_files[original_index] = new_file_path
        current_details = app_instance.reviewable_segment_details.get(app_instance.current_gui_selection)
        if current_details:
            current_details['audio_path'] = new_file_path
            print(f"TTSDevGUI: Updated reviewable_segment_details[{app_instance.current_gui_selection}]['audio_path'] to {new_file_path}")
        else:
            print(f"TTSDevGUI: Warning - Could not find details for GUI index {app_instance.current_gui_selection} to update audio_path.")

        widgets.update_segment_display_name(app_instance, app_instance.current_gui_selection, new_file_path)

        try:
            if old_file_path and os.path.exists(old_file_path) and old_file_path != new_file_path:
                os.remove(old_file_path)
                print(f"TTSDevGUI: Removed old file: {old_file_path}")
        except Exception as e:
            print(f"TTSDevGUI: Warning - Failed to remove old file {old_file_path}: {e}")

        if not app_instance.player.load_file(new_file_path):
             messagebox.showerror("Load Error", f"Segment regenerated, but failed to load new audio:\n{new_file_path}")
             widgets.clear_waveform(app_instance)
        else:
             messagebox.showinfo("Success", "Segment regenerated and loaded.")
             widgets.update_waveform(app_instance, new_file_path)
        
    else:
        messagebox.showerror("Error", "Failed to regenerate speech segment. Check console output. Keeping original segment.")
        if old_file_path and os.path.exists(old_file_path):
            if not app_instance.player.load_file(old_file_path):
                print(f"TTSDevGUI: Failed to reload original file {old_file_path} after redo failure.")
                widgets.clear_waveform(app_instance)
            else:
                widgets.update_waveform(app_instance, old_file_path)
        else:
            app_instance.player.load_file(None)
            widgets.clear_waveform(app_instance)