from flask import Flask, render_template, request, jsonify, send_from_directory, Response
import subprocess
import os
import threading
import queue
import json
import re # Import re for regex parsing
import traceback
import datetime # Import datetime for timestamping

# Global queue to hold output from the subprocess
output_queue = queue.Queue()

# Global variable to store the process thread
process_thread = None

# Global variable to store the subprocess object
current_process = None

# Global variable to store the final output files (video)
final_output_files = []

# Global variable to indicate if the process is running
process_running = False

podcast_gui_app = Flask(__name__)
# Directory to save uploaded files relative to the podcast_gui.py location
podcast_gui_app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
# Directory for generated outputs relative to the podcast_gui.py location
podcast_gui_app.config['OUTPUT_FOLDER'] = os.path.join(os.path.dirname(__file__), 'outputs')
podcast_gui_app.config['ARCHIVE_DIR'] = os.path.join(os.path.dirname(__file__), 'outputs', 'archive')


# Ensure upload and output folders exist
os.makedirs(podcast_gui_app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(podcast_gui_app.config['OUTPUT_FOLDER'], exist_ok=True)
os.makedirs(podcast_gui_app.config['ARCHIVE_DIR'], exist_ok=True)

# --- Routes ---
@podcast_gui_app.route('/')
def index():
    """Render the main podcast generation page."""
    return render_template('podcast_gui.html')

@podcast_gui_app.route('/generate_podcast_audio_video', methods=['POST'])
def generate_podcast_audio_video():
    """Handle podcast generation requests and start the process."""
    global process_thread, process_running, final_output_files

    if process_running:
        return jsonify({"status": "error", "message": "A podcast generation process is already running."}), 409 # Conflict

    data = request.form
    uploaded_files = request.files

    # Construct the base command to run podcast_builder.py
    # The command should be executed from the Ecne-AI-Podcasterv2 directory
    script_path = os.path.join(os.path.dirname(__file__), 'podcast_builder.py')
    command = ['python', script_path]

    # Force --dev mode
    command.append('--dev')

    # Handle --script
    script_file = uploaded_files.get('script_file')

    if script_file and script_file.filename:
        filepath = os.path.join(podcast_gui_app.config['UPLOAD_FOLDER'], script_file.filename)
        script_file.save(filepath)
        command.extend(['--script', filepath])
    else:
        return jsonify({"status": "error", "message": "A script file must be provided."}), 400

    # Map form fields to podcast_builder.py command-line arguments
    arg_map = {
        'host_voice': '--host-voice',
        'guest_voice': '--guest-voice',
        'silence': '--silence',
        'voice': '--voice',
        'speed': '--speed',
        'port': '--port',
        'api_host': '--api-host',
        'output_filename': '--output', # Optional output filename
        'video_resolution': '--video-resolution',
        'video_fps': '--video-fps',
        'video_character_scale': '--video-character-scale',
        'video_fade': '--video-fade',
        'video_intermediate_preset': '--video-intermediate-preset',
        'video_intermediate_crf': '--video-intermediate-crf',
        'video_final_audio_bitrate': '--video-final-audio-bitrate',
        'video_workers': '--video-workers',
    }

    for field, arg in arg_map.items():
        value = data.get(field)
        if value:
            # Special handling for numeric values that might be empty strings
            if field in ['silence', 'speed', 'port', 'video_fps', 'video_character_scale', 'video_fade', 'video_intermediate_crf', 'video_workers']:
                try:
                    if value.strip() != '': # Only convert if not empty
                        command.extend([arg, str(float(value) if '.' in value else int(value))])
                except ValueError:
                    return jsonify({"status": "error", "message": f"Invalid numeric value for {field}: {value}"}), 400
            else:
                command.extend([arg, value])

    # Handle boolean flags
    boolean_flags = {
        'guest_breakup': '--guest-breakup',
        'video_keep_temp': '--video-keep-temp',
    }

    for field, arg in boolean_flags.items():
        if data.get(field) == 'on': # Checkbox value is 'on' when checked
            command.append(arg)

    print(f"Executing command: {' '.join(command)}")

    # Clear previous output and results
    while not output_queue.empty():
        try:
            output_queue.get_nowait()
        except queue.Empty:
            pass
    final_output_files = []

    # Execute the command in a separate thread for streaming
    process_running = True
    # Run the script from the Ecne-AI-Podcasterv2 directory
    process_thread = threading.Thread(target=run_podcast_builder, args=(command, os.path.dirname(__file__)))
    process_thread.start()

    return jsonify({"status": "processing", "message": "Podcast generation started. Please wait for progress."})

@podcast_gui_app.route('/stream_output')
def stream_output():
    """Streams output from the podcast generation subprocess using Server-Sent Events."""
    def generate():
        while process_running or not output_queue.empty():
            try:
                # Get output line from the queue with a timeout
                line = output_queue.get(timeout=1)
                if line is None: # Sentinel value to indicate end of process
                    break

                # Parse for total segments
                total_segments_match = re.search(r"Found (\d+) valid dialogue segments.", line)
                if total_segments_match:
                    yield f"data: {json.dumps({'type': 'total_segments', 'count': int(total_segments_match.group(1))})}\n\n"
                    continue

                # Parse for segment progress
                segment_progress_match = re.search(r"Segment (\d+) \(Line \d+\):", line)
                if segment_progress_match:
                    yield f"data: {json.dumps({'type': 'segment_progress', 'current': int(segment_progress_match.group(1))})}\n\n"
                    continue
                
                # Parse for GUI active
                if "Entering development mode for segment review..." in line:
                    yield f"data: {json.dumps({'type': 'gui_active', 'content': 'Pygame GUI active, awaiting user interaction...'})}\n\n"
                    continue

                # Parse for final video path
                video_path_match = re.search(r"Video generation process initiated for (.+?\.mp4)\.", line)
                if video_path_match:
                    # Extract the relative path for serving
                    full_path = video_path_match.group(1)
                    # Assuming video_output_path is within FINAL_AUDIO_OUTPUT_DIR which is outputs/final
                    # Need to make it relative to the base outputs directory for serving
                    relative_path = os.path.relpath(full_path, podcast_gui_app.config['OUTPUT_FOLDER'])
                    final_output_files.append(relative_path)
                    yield f"data: {json.dumps({'type': 'video_ready', 'path': relative_path})}\n\n"
                    continue

                # Format as SSE data for general output
                yield f"data: {json.dumps({'type': 'output', 'content': line})}\n\n"
            except queue.Empty:
                # No output in the last second, keep the connection alive
                yield "data: {}\n\n" # Send a keep-alive message (empty JSON)
            except Exception as e:
                 print(f"Error streaming output: {e}")
                 yield f"data: {json.dumps({'type': 'error', 'content': f'Streaming error: {e}'})}\n\n"
                 break

        # After the process finishes, send the final output file paths
        yield f"data: {json.dumps({'type': 'complete', 'output_files': final_output_files})}\n\n"


    # Set up the response for Server-Sent Events
    response = Response(generate(), mimetype='text/event-stream')
    response.headers['X-Accel-Buffering'] = 'no' # Disable buffering for Nginx
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['Connection'] = 'keep-alive'
    return response

@podcast_gui_app.route('/outputs/<path:filename>')
def serve_output(filename):
    """Serve generated output files (videos) from the outputs directory."""
    try:
        # Serve from the outputs directory relative to podcast_gui.py
        return send_from_directory(podcast_gui_app.config['OUTPUT_FOLDER'], filename)
    except FileNotFoundError:
        return "Output file not found.", 404

@podcast_gui_app.route('/stop_podcast_process', methods=['POST'])
def stop_podcast_process():
    """Stops the currently running podcast generation process."""
    global current_process, process_running
    if current_process and process_running:
        try:
            current_process.terminate() # or .kill() for a more forceful stop
            # Wait a short time for termination
            current_process.wait(timeout=5)
            process_running = False
            current_process = None
            return jsonify({"status": "success", "message": "Podcast generation process stopped."})
        except Exception as e:
            return jsonify({"status": "error", "message": f"Error stopping process: {e}"}), 500
    else:
        return jsonify({"status": "info", "message": "No podcast generation process is currently running."})

def run_podcast_builder(command, cwd):
    """Runs the podcast_builder.py script as a subprocess and streams output to a queue."""
    global process_running, final_output_files, current_process
    process = None
    try:
        # Execute the command in the specified current working directory (Ecne-AI-Podcasterv2)
        process = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        current_process = process # Store the process object globally

        # Read output line by line and put it in the queue
        for line in iter(process.stdout.readline, ''):
            output_queue.put(line)

        # Wait for the process to finish
        process.wait()

        if process.returncode == 0:
            output_queue.put("--- Podcast Generation Complete ---")
            # The final video path is captured by the stream_output generator
        else:
            output_queue.put(f"--- Podcast Generation Failed (Exit Code {process.returncode}) ---")
            # Optionally put stderr content if not already streamed
            # output_queue.put(process.stderr.read()) # If stderr was not merged

    except FileNotFoundError:
        output_queue.put("Error: python or podcast_builder.py not found. Ensure Python is in your PATH and podcast_builder.py exists.")
    except Exception as e:
        output_queue.put(f"An unexpected error occurred during subprocess execution: {e}")
        output_queue.put(traceback.format_exc())
    finally:
        # Signal the end of the process
        output_queue.put(None)
        process_running = False
        current_process = None # Clear the process object


if __name__ == '__main__':
    # In a production environment, use a production-ready WSGI server like Gunicorn or uWSGI
    # For development, debug=True is fine.
    # Running from the Ecne-AI-Podcasterv2 directory
    podcast_gui_app.run(debug=True, port=5001) # Use a different port to avoid conflict with web_app.py