from flask import Flask, render_template, request, jsonify, send_from_directory, Response
import subprocess
import os
import threading
import queue
import json
import yaml
from dotenv import load_dotenv, set_key
import traceback

# Load environment variables from .env file at the start
# Assumes .env is in the Ecne-AI-Podcasterv2 directory
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

# Global queue to hold output from the subprocess
output_queue = queue.Queue()

# Global variable to store the process thread
process_thread = None

# Global variable to store the subprocess object
current_process = None

# Global variable to store the final output files (script, audio)
final_output_files = []

# Global variable to indicate if the process is running
process_running = False

app = Flask(__name__)
# Directory to save uploaded files relative to the web_app.py location
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
# Directory for generated outputs relative to the web_app.py location
app.config['OUTPUT_FOLDER'] = os.path.join(os.path.dirname(__file__), 'outputs')


# Ensure upload and output folders exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

# --- Routes ---
@app.route('/')
def index():
    """Render the main podcast generation page."""
    llm_settings = load_llm_settings()
    available_models = list(llm_settings.keys()) if llm_settings else []
    return render_template('index.html', llm_models=available_models)

@app.route('/settings')
def settings():
    """Render the settings page."""
    api_keys = load_api_keys()
    llm_settings = load_llm_settings()
    return render_template('settings.html', api_keys=api_keys, llm_settings=llm_settings)

@app.route('/get_llm_models', methods=['GET'])
def get_llm_models():
    """Return the list of available LLM models."""
    llm_settings = load_llm_settings()
    available_models = list(llm_settings.keys()) if llm_settings else []
    return jsonify({"llm_models": available_models})

@app.route('/generate_podcast', methods=['POST'])
def generate_podcast():
    """Handle podcast generation requests and start the process."""
    global process_thread, process_running, final_output_files

    if process_running:
        return jsonify({"status": "error", "message": "A podcast generation process is already running."}), 409 # Conflict

    data = request.form
    uploaded_files = request.files

    # Construct the base command to run script_builder.py
    # The command should be executed from the Ecne-AI-Podcasterv2 directory
    script_path = os.path.join(os.path.dirname(__file__), 'script_builder.py')
    command = ['python', script_path]

    # Map form fields to script_builder.py command-line arguments
    arg_map = {
        'topic': '--topic',
        'keywords': '--keywords', # Corrected mapping based on script_builder.py usage
        'guidance': '--guidance',
        'api': '--api',
        'llm-model': '--llm-model',
        'max-web-results': '--max-web-results',
        'max-reddit-results': '--max-reddit-results',
        'max-reddit-comments': '--max-reddit-comments',
        'per-keyword-results': '--per-keyword-results',
        'score-threshold': '--score-threshold',
    }

    for field, arg in arg_map.items():
        value = data.get(field)
        if value:
            command.extend([arg, value])

    # Handle boolean flags
    boolean_flags = {
        'combine-keywords': '--combine-keywords',
        'no-search': '--no-search',
        'reference-docs-summarize': '--reference-docs-summarize',
        'skip_refinement': '--skip-refinement',
        'no-reddit': '--no-reddit',
        'report': '--report',
        'skip-audio': '--skip-audio',
    }

    for field, arg in boolean_flags.items():
        if data.get(field) == 'on': # Checkbox value is 'on' when checked
            command.append(arg)

    # Handle uploaded files and folders (adjust based on script_builder.py's args)
    uploaded_ref_docs_paths = []
    if 'reference-docs' in uploaded_files:
        for file in uploaded_files.getlist('reference-docs'):
            if file.filename:
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
                file.save(filepath)
                uploaded_ref_docs_paths.append(filepath)
    if uploaded_ref_docs_paths:
        command.extend(['--reference-docs', ','.join(uploaded_ref_docs_paths)])

    if 'direct-articles' in uploaded_files:
        file = uploaded_files['direct-articles']
        if file.filename:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(filepath)
            command.extend(['--direct-articles', filepath])

    # Handle folder upload for reference docs folder
    uploaded_folder_files = uploaded_files.getlist('reference-docs-folder')
    if uploaded_folder_files:
         # Find the first file's directory relative to the upload folder
         first_file = uploaded_folder_files[0]
         if first_file.filename:
              # The filename includes the relative path from the dropped folder, e.g., 'my_folder/file1.txt'
              relative_folder_path = os.path.dirname(first_file.filename)
              if relative_folder_path:
                   folder_path_in_uploads = os.path.join(app.config['UPLOAD_FOLDER'], relative_folder_path)
                   # Save all files in the folder
                   for file in uploaded_folder_files:
                        if file.filename:
                             filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
                             os.makedirs(os.path.dirname(filepath), exist_ok=True)
                             file.save(filepath)
                   command.extend(['--reference-docs-folder', folder_path_in_uploads])
    # Note: The original code had a 'pass' here if no folder files, which is fine.


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
    process_thread = threading.Thread(target=run_script_builder, args=(command, os.path.dirname(__file__)))
    process_thread.start()

    return jsonify({"status": "processing", "message": "Podcast generation started. Please wait for progress."})

@app.route('/stream_output')
def stream_output():
    """Streams output from the podcast generation subprocess using Server-Sent Events."""
    def generate():
        while process_running or not output_queue.empty():
            try:
                # Get output line from the queue with a timeout
                line = output_queue.get(timeout=1)
                if line is None: # Sentinel value to indicate end of process
                    break
                # Format as SSE data
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

@app.route('/outputs/<path:filename>')
def serve_output(filename):
    """Serve generated output files (scripts, audio, reports) from the outputs directory."""
    try:
        # Serve from the outputs directory relative to web_app.py
        return send_from_directory(app.config['OUTPUT_FOLDER'], filename)
    except FileNotFoundError:
        return "Output file not found.", 404

@app.route('/save_settings', methods=['POST'])
def save_settings():
    """Handle saving API keys and LLM settings."""
    data = request.json
    api_keys_data = data.get('apiKeys', {})
    llm_settings_data = data.get('llmSettings', {})

    api_success, api_message = save_api_keys(api_keys_data)
    llm_success, llm_message = save_llm_settings(llm_settings_data)

    if api_success and llm_success:
        return jsonify({"status": "success", "message": "Settings saved successfully."})
    else:
        # Combine messages for partial failures
        error_message = ""
        if not api_success:
            error_message += f"API Keys Save Failed: {api_message} "
        if not llm_success:
            error_message += f"LLM Settings Save Failed: {llm_message}"
        return jsonify({"status": "error", "message": error_message.strip()}), 500

# --- Helper Functions ---

def load_api_keys():
    """Loads API keys from environment variables (loaded from .env)."""
    # load_dotenv() is called at the app startup, so env vars should be available
    # Add other keys used by script_builder if necessary
    return {
        "GOOGLE_API_KEY": os.getenv("GOOGLE_API_KEY", ""),
        "GOOGLE_CSE_ID": os.getenv("GOOGLE_CSE_ID", ""),
        "BRAVE_API_KEY": os.getenv("BRAVE_API_KEY", ""),
        "REDDIT_CLIENT_ID": os.getenv("REDDIT_CLIENT_ID", ""),
        "REDDIT_CLIENT_SECRET": os.getenv("REDDIT_CLIENT_SECRET", ""),
        "REDDIT_USER_AGENT": os.getenv("REDDIT_USER_AGENT", ""),
        # Add any other API keys script_builder might use
    }

def load_llm_settings():
    """Loads LLM model configurations from settings/llm_settings/ai_models.yml."""
    # Path relative to web_app.py
    llm_config_path = os.path.join(os.path.dirname(__file__), 'settings', 'llm_settings', 'ai_models.yml')
    if not os.path.exists(llm_config_path):
        print(f"Warning: LLM configuration file not found at {llm_config_path}")
        return {}
    try:
        with open(llm_config_path, 'r', encoding='utf-8') as f:
            settings = yaml.safe_load(f)
            return settings if isinstance(settings, dict) else {}
    except yaml.YAMLError as e:
        print(f"Error parsing LLM configuration file {llm_config_path}: {e}")
        return {}
    except Exception as e:
        print(f"An unexpected error occurred loading LLM settings: {e}")
        return {}

def save_api_keys(api_keys_data):
    """Saves API keys to the .env file."""
    # Path relative to web_app.py
    dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
    # Ensure the .env file exists
    if not os.path.exists(dotenv_path):
        try:
            with open(dotenv_path, 'w') as f:
                pass # Create empty file
        except IOError as e:
             print(f"Error creating .env file at {dotenv_path}: {e}")
             return False, f"Error creating .env file: {e}"


    try:
        for key, value in api_keys_data.items():
            # set_key handles adding/updating keys
            set_key(dotenv_path, key, value)
        print(f"API keys saved to {dotenv_path}")
        return True, "API keys saved successfully."
    except Exception as e:
        print(f"Error saving API keys to {dotenv_path}: {e}")
        return False, f"Error saving API keys: {e}"

def save_llm_settings(llm_settings_data):
    """Saves LLM model configurations to settings/llm_settings/ai_models.yml."""
    # Path relative to web_app.py
    llm_config_dir = os.path.join(os.path.dirname(__file__), 'settings', 'llm_settings')
    llm_config_path = os.path.join(llm_config_dir, 'ai_models.yml')

    # Ensure the directory exists
    os.makedirs(llm_config_dir, exist_ok=True)

    try:
        with open(llm_config_path, 'w', encoding='utf-8') as f:
            yaml.dump(llm_settings_data, f, default_flow_style=False, sort_keys=False)
        print(f"LLM settings saved to {llm_config_path}")
        return True, "LLM settings saved successfully."
    except Exception as e:
        print(f"Error saving LLM settings to {llm_config_path}: {e}")
        return False, f"Error saving LLM settings: {e}"

def run_script_builder(command, cwd):
    """Runs the script_builder.py script as a subprocess and streams output to a queue."""
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
            # Find generated output files (script, audio, report if generated)
            final_output_files = find_output_files(cwd) # Pass cwd to find files
            output_queue.put(f"Generated files: {', '.join(final_output_files)}")
        else:
            output_queue.put(f"--- Podcast Generation Failed (Exit Code {process.returncode}) ---")
            # Optionally put stderr content if not already streamed
            # output_queue.put(process.stderr.read()) # If stderr was not merged

    except FileNotFoundError:
        output_queue.put("Error: python or script_builder.py not found. Ensure Python is in your PATH and script_builder.py exists.")
    except Exception as e:
        output_queue.put(f"An unexpected error occurred during subprocess execution: {e}")
        output_queue.put(traceback.format_exc())
    finally:
        # Signal the end of the process
        output_queue.put(None)
        process_running = False
        current_process = None # Clear the process object


def find_output_files(base_dir):
    """Finds the most recently generated output files in the outputs/ directory."""
    # The outputs directory is created within the run-specific timestamped folder
    # We need to find the latest timestamped folder first
    outputs_base_dir = os.path.join(base_dir, 'outputs')
    if not os.path.exists(outputs_base_dir):
        return []

    # List all items in the outputs base directory
    all_items = [os.path.join(outputs_base_dir, item) for item in os.listdir(outputs_base_dir)]

    # Filter for directories (the timestamped run folders)
    run_dirs = [item for item in all_items if os.path.isdir(item)]

    # Sort directories by modification time (most recent first)
    run_dirs.sort(key=os.path.getmtime, reverse=True)

    if not run_dirs:
        return []

    # The latest run directory is the first one
    latest_run_dir = run_dirs[0]
    print(f"Looking for output files in: {latest_run_dir}")

    # List all files within the latest run directory
    try:
        files_in_latest_run = [os.path.join(latest_run_dir, f) for f in os.listdir(latest_run_dir) if os.path.isfile(os.path.join(latest_run_dir, f))]
    except OSError as e:
        print(f"Error listing files in {latest_run_dir}: {e}")
        return []


    # Filter for relevant output files (e.g., .txt script, .mp3 audio, .md/.pdf report)
    output_files = [f for f in files_in_latest_run if f.endswith('.txt') or f.endswith('.mp3') or f.endswith('.md') or f.endswith('.pdf')]

    # Return paths relative to the outputs base directory for serving
    relative_paths = [os.path.relpath(f, outputs_base_dir) for f in output_files]

    return relative_paths


@app.route('/stop_podcast', methods=['POST'])
def stop_podcast():
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

if __name__ == '__main__':
    # In a production environment, use a production-ready WSGI server like Gunicorn or uWSGI
    # For development, debug=True is fine.
    # Running from the Ecne-AI-Podcasterv2 directory
    app.run(debug=True, port=5000) # Use a different port if 5000 is in use