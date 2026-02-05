from flask import Flask, render_template, request, jsonify, send_from_directory, Response
import subprocess
import os
import threading
import queue
import json
import re
import yaml
from dotenv import load_dotenv, set_key
import traceback
import datetime
import time
import requests
from functions.ai import call_ai_api

# Load environment variables from .env file at the start
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

# Global dictionary to manage active processes
# Key: process_type (e.g., 'script_builder', 'podcast_builder')
# Value: { 'output_queue': queue.Queue(), 'process_thread': threading.Thread, 'current_process': subprocess.Popen, 'running': bool, 'final_output_files': list }
active_processes = {}

control_panel_app = Flask(__name__)

# Directory to save uploaded files
control_panel_app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
# Directory for generated outputs
control_panel_app.config['OUTPUT_FOLDER'] = os.path.join(os.path.dirname(__file__), 'outputs')
control_panel_app.config['ARCHIVE_DIR'] = os.path.join(os.path.dirname(__file__), 'outputs', 'archive')

# Ensure upload and output folders exist
os.makedirs(control_panel_app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(control_panel_app.config['OUTPUT_FOLDER'], exist_ok=True)
os.makedirs(control_panel_app.config['ARCHIVE_DIR'], exist_ok=True)

# --- Helper Functions (Migrated from web_app.py) ---

def load_api_keys():
    """Loads API keys from environment variables (loaded from .env)."""
    return {
        "GOOGLE_API_KEY": os.getenv("GOOGLE_API_KEY", ""),
        "GOOGLE_CSE_ID": os.getenv("GOOGLE_CSE_ID", ""),
        "BRAVE_API_KEY": os.getenv("BRAVE_API_KEY", ""),
        "REDDIT_CLIENT_ID": os.getenv("REDDIT_CLIENT_ID", ""),
        "REDDIT_CLIENT_SECRET": os.getenv("REDDIT_CLIENT_SECRET", ""),
        "REDDIT_USER_AGENT": os.getenv("REDDIT_USER_AGENT", ""),
    }

def load_llm_settings():
    """Loads LLM model configurations from settings/llm_settings/ai_models.yml."""
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
    dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
    if not os.path.exists(dotenv_path):
        try:
            with open(dotenv_path, 'w') as f:
                pass
        except IOError as e:
             print(f"Error creating .env file at {dotenv_path}: {e}")
             return False, f"Error creating .env file: {e}"

    try:
        for key, value in api_keys_data.items():
            set_key(dotenv_path, key, value)
        print(f"API keys saved to {dotenv_path}")
        return True, "API keys saved successfully."
    except Exception as e:
        print(f"Error saving API keys to {dotenv_path}: {e}")
        return False, f"Error saving API keys: {e}"

def save_llm_settings(llm_settings_data):
    """Saves LLM model configurations to settings/llm_settings/ai_models.yml."""
    llm_config_dir = os.path.join(os.path.dirname(__file__), 'settings', 'llm_settings')
    llm_config_path = os.path.join(llm_config_dir, 'ai_models.yml')

    os.makedirs(llm_config_dir, exist_ok=True)

    try:
        with open(llm_config_path, 'w', encoding='utf-8') as f:
            yaml.dump(llm_settings_data, f, default_flow_style=False, sort_keys=False)
        print(f"LLM settings saved to {llm_config_path}")
        return True, "LLM settings saved successfully."
    except Exception as e:
        print(f"Error saving LLM settings to {llm_config_path}: {e}")
        return False, f"Error saving LLM settings: {e}"

def find_output_files(base_dir):
    """Finds the most recently generated output files in their respective directories."""
    outputs_base_dir = os.path.join(base_dir, 'outputs')
    if not os.path.exists(outputs_base_dir):
        return []

    final_files = []
    
    # Define directories for each output type
    scripts_dir = os.path.join(outputs_base_dir, 'scripts')
    reports_dir = os.path.join(outputs_base_dir, 'reports')
    youtube_dir = os.path.join(outputs_base_dir, 'youtube_descriptions')

    # Helper to find the latest file in a directory
    def find_latest_file(directory, suffix):
        if not os.path.exists(directory):
            return None
        try:
            files = [f for f in os.listdir(directory) if f.endswith(suffix)]
            if files:
                files.sort(key=lambda x: os.path.getmtime(os.path.join(directory, x)), reverse=True)
                return files[0]
        except OSError as e:
            print(f"Error listing files in {directory}: {e}")
        return None

    # Find the latest script
    latest_script = find_latest_file(scripts_dir, '_podcast_script.txt')
    if latest_script:
        final_files.append(f"scripts/{latest_script}")

    # Find the latest report
    latest_report = find_latest_file(reports_dir, '_report.txt')
    if latest_report:
        final_files.append(f"reports/{latest_report}")

    # Find the latest YouTube description
    latest_youtube_desc = find_latest_file(youtube_dir, '.md')
    if latest_youtube_desc:
        final_files.append(f"youtube_descriptions/{latest_youtube_desc}")

    return final_files

# --- Docker Management Functions ---

def get_docker_path():
    """Get the path to the Orpheus-FastAPI Docker setup directory."""
    return os.path.join(os.path.dirname(__file__), 'orpheus_tts_setup', 'Orpheus-FastAPI')

def get_docker_compose_command():
    """Get the appropriate docker-compose command based on platform and availability."""
    import platform
    
    # Try docker compose (V2) first
    try:
        result = subprocess.run(['docker', 'compose', 'version'],
                               capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return ['docker', 'compose']
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    
    # Fall back to docker-compose (V1)
    try:
        result = subprocess.run(['docker-compose', '--version'],
                               capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return ['docker-compose']
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    
    # If we're on Windows, also try with .exe extension
    if platform.system() == 'Windows':
        try:
            result = subprocess.run(['docker-compose.exe', '--version'],
                                   capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return ['docker-compose.exe']
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
    
    return None

def check_docker_status():
    """Check if Orpheus-FastAPI Docker containers are running."""
    docker_path = get_docker_path()
    if not os.path.exists(docker_path):
        return {
            'status': 'not_installed',
            'message': 'Orpheus-FastAPI not found. Please run the installer first.',
            'containers': []
        }
    
    docker_compose_cmd = get_docker_compose_command()
    if not docker_compose_cmd:
        return {
            'status': 'error',
            'message': 'Docker Compose not found. Please install Docker Desktop.',
            'containers': []
        }
    
    try:
        # Check if docker-compose is running
        cmd = docker_compose_cmd + ['-f', 'docker-compose-gpu.yml', 'ps']
        result = subprocess.run(cmd, cwd=docker_path, capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            output_lines = result.stdout.strip().split('\n')
            containers = []
            building_containers = []
            
            # Parse docker-compose ps output
            for line in output_lines[1:]:  # Skip header
                if line.strip():
                    parts = line.split()
                    if len(parts) >= 4:
                        name = parts[0]
                        status = ' '.join(parts[3:])  # Status might have multiple words
                        is_running = 'Up' in status
                        is_building = any(keyword in status for keyword in ['Restarting', 'Starting', 'Created'])
                        
                        containers.append({
                            'name': name,
                            'status': status,
                            'running': is_running,
                            'building': is_building
                        })
                        
                        if is_building:
                            building_containers.append(name)
            
            # Check if any containers are running
            running_containers = [c for c in containers if c['running']]
            
            if running_containers:
                return {
                    'status': 'running',
                    'message': f'{len(running_containers)} container(s) running',
                    'containers': containers
                }
            elif building_containers:
                return {
                    'status': 'building',
                    'message': f'Containers starting/building ({len(building_containers)} containers). Please wait...',
                    'containers': containers
                }
            else:
                return {
                    'status': 'stopped',
                    'message': 'Docker containers are stopped',
                    'containers': containers
                }
        else:
            error_message = result.stderr
            # Check for common Windows Docker Desktop not running errors
            if 'dockerDesktopLinuxEngine' in error_message or 'The system cannot find the file specified' in error_message:
                return {
                    'status': 'error',
                    'message': 'Docker Desktop is not running. Please start Docker Desktop and try again.',
                    'containers': []
                }
            else:
                return {
                    'status': 'error',
                    'message': f'Docker command failed: {error_message}',
                    'containers': []
                }
    
    except subprocess.TimeoutExpired:
        return {
            'status': 'error',
            'message': 'Docker command timed out',
            'containers': []
        }
    except FileNotFoundError:
        return {
            'status': 'error',
            'message': 'Docker or docker-compose not found. Please install Docker.',
            'containers': []
        }
    except Exception as e:
        return {
            'status': 'error',
            'message': f'Error checking Docker status: {str(e)}',
            'containers': []
        }

def start_docker_containers():
    """Start Orpheus-FastAPI Docker containers in detached mode."""
    docker_path = get_docker_path()
    if not os.path.exists(docker_path):
        return {'success': False, 'message': 'Orpheus-FastAPI not found. Please run the installer first.'}
    
    docker_compose_cmd = get_docker_compose_command()
    if not docker_compose_cmd:
        return {'success': False, 'message': 'Docker Compose not found. Please install Docker Desktop.'}
    
    try:
        # Start containers in detached mode with longer timeout for initial builds
        cmd = docker_compose_cmd + ['-f', 'docker-compose-gpu.yml', 'up', '-d']
        result = subprocess.run(cmd, cwd=docker_path, capture_output=True, text=True, timeout=300)  # 5 minutes for initial build
        
        if result.returncode == 0:
            return {
                'success': True,
                'message': 'Docker containers started successfully. If this is the first run, it may take several minutes to download models and build containers. Services will be available at http://127.0.0.1:5005 when ready.',
                'output': result.stdout
            }
        else:
            # Check if it's a build/download process that's still running
            if 'Pulling' in result.stderr or 'Building' in result.stderr or 'Downloading' in result.stderr:
                return {
                    'success': True,
                    'message': 'Docker containers are building/downloading. This may take 10-15 minutes for the first run (downloading 4GB+ models). Check back in a few minutes.',
                    'output': result.stderr
                }
            else:
                error_message = result.stderr
                # Check for common Windows Docker Desktop not running errors
                if 'dockerDesktopLinuxEngine' in error_message or 'The system cannot find the file specified' in error_message:
                    return {
                        'success': False,
                        'message': 'Docker Desktop is not running. Please start Docker Desktop and try again.',
                        'output': error_message
                    }
                else:
                    return {
                        'success': False,
                        'message': f'Failed to start Docker containers: {error_message}',
                        'output': error_message
                    }
    
    except subprocess.TimeoutExpired:
        return {
            'success': True,  # Changed to True since timeout during build is normal
            'message': 'Docker start command timed out (5 minutes). This is normal for first-time setup. Containers are likely still building/downloading in the background. Check status in a few minutes.'
        }
    except Exception as e:
        return {'success': False, 'message': f'Error starting Docker containers: {str(e)}'}

def stop_docker_containers():
    """Stop Orpheus-FastAPI Docker containers."""
    docker_path = get_docker_path()
    if not os.path.exists(docker_path):
        return {'success': False, 'message': 'Orpheus-FastAPI not found.'}
    
    docker_compose_cmd = get_docker_compose_command()
    if not docker_compose_cmd:
        return {'success': False, 'message': 'Docker Compose not found. Please install Docker Desktop.'}
    
    try:
        cmd = docker_compose_cmd + ['-f', 'docker-compose-gpu.yml', 'down']
        result = subprocess.run(cmd, cwd=docker_path, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            return {
                'success': True,
                'message': 'Docker containers stopped successfully.',
                'output': result.stdout
            }
        else:
            return {
                'success': False,
                'message': f'Failed to stop Docker containers: {result.stderr}',
                'output': result.stderr
            }
    
    except subprocess.TimeoutExpired:
        return {'success': False, 'message': 'Docker stop command timed out (30s).'}
    except Exception as e:
        return {'success': False, 'message': f'Error stopping Docker containers: {str(e)}'}

# --- Qwen3 TTS Service Functions ---

def check_qwen3_status():
    """Check if Qwen3 TTS service is running via health endpoint."""
    qwen3_port = os.getenv('QWEN3_PORT', '8000')
    health_url = f"http://127.0.0.1:{qwen3_port}/health"
    
    try:
        response = requests.get(health_url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            
            # Also check model status
            models_status = get_qwen3_models_status(qwen3_port)
            
            return {
                'status': 'running',
                'message': 'Qwen3 TTS service is running',
                'provider': data.get('provider', 'qwen3'),
                'model': data.get('model', 'unknown'),
                'voices_available': data.get('voices_available', 0),
                'url': health_url,
                'models': models_status
            }
        else:
            return {
                'status': 'error',
                'message': f'Qwen3 TTS returned status {response.status_code}',
                'url': health_url
            }
    except requests.exceptions.ConnectionError:
        return {
            'status': 'stopped',
            'message': 'Qwen3 TTS service is not running (connection refused)',
            'url': health_url
        }
    except requests.exceptions.Timeout:
        return {
            'status': 'timeout',
            'message': 'Qwen3 TTS service timed out (may be starting up)',
            'url': health_url
        }
    except Exception as e:
        return {
            'status': 'error',
            'message': f'Error checking Qwen3 TTS status: {str(e)}',
            'url': health_url
        }


def get_qwen3_models_status(port):
    """Get model download/load status from Qwen3 API."""
    try:
        response = requests.get(f"http://127.0.0.1:{port}/v1/models/status", timeout=5)
        if response.status_code == 200:
            models = response.json()
            # Filter to main models of interest
            main_models = ['qwen3-tts-1.7b-base', 'qwen3-tts-1.7b-customvoice']
            return [m for m in models if m['model_id'] in main_models]
        return []
    except:
        return []

def start_qwen3_service():
    """Start Qwen3 TTS service."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    qwen3_dir = os.path.join(script_dir, 'EcneAI-Qwen-3-TTS-api')
    
    if not os.path.exists(qwen3_dir):
        return {
            'success': False,
            'message': 'Qwen3 TTS service not found. Please run the installer first.'
        }
    
    # Check if already running
    status = check_qwen3_status()
    if status['status'] == 'running':
        return {'success': True, 'message': 'Qwen3 TTS service is already running'}
    
    try:
        # Determine activation script based on OS
        if os.name == 'nt':  # Windows
            activate_script = os.path.join(qwen3_dir, 'venv', 'Scripts', 'activate.bat')
            cmd = f'call "{activate_script}" && python -m uvicorn api.main:app --host 127.0.0.1 --port 8000'
            # Start in a new process
            subprocess.Popen(
                cmd,
                cwd=qwen3_dir,
                shell=True,
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
        else:  # Linux/Mac
            activate_script = os.path.join(qwen3_dir, 'venv', 'bin', 'activate')
            cmd = f'source "{activate_script}" && python -m uvicorn api.main:app --host 127.0.0.1 --port 8000'
            # Start with nohup to keep running after parent exits
            subprocess.Popen(
                ['bash', '-c', f'cd "{qwen3_dir}" && {cmd} > ../logs/qwen3_service.log 2>&1 &'],
                shell=False
            )
        
        # Wait a moment and check if it started
        time.sleep(3)
        status = check_qwen3_status()
        if status['status'] == 'running':
            return {'success': True, 'message': 'Qwen3 TTS service started successfully'}
        else:
            return {
                'success': True,
                'message': 'Qwen3 TTS service is starting (may take a moment to be ready)'
            }
            
    except Exception as e:
        return {'success': False, 'message': f'Error starting Qwen3 TTS service: {str(e)}'}

def stop_qwen3_service():
    """Stop Qwen3 TTS service by finding and killing the process."""
    try:
        # Find uvicorn processes on port 8000
        if os.name == 'nt':  # Windows
            result = subprocess.run(
                ['tasklist', '/FI', 'IMAGENAME eq python.exe', '/FO', 'CSV'],
                capture_output=True, text=True
            )
            # Look for uvicorn in the command line
            result2 = subprocess.run(
                ['wmic', 'process', 'where', 'name="python.exe"', 'get', 'ProcessId,CommandLine', '/format:csv'],
                capture_output=True, text=True
            )
            
            # Parse and kill uvicorn processes
            killed = False
            for line in result2.stdout.split('\n'):
                if 'uvicorn' in line.lower() and '8000' in line:
                    parts = line.strip().split(',')
                    if len(parts) >= 2:
                        try:
                            pid = int(parts[-1])
                            subprocess.run(['taskkill', '/PID', str(pid), '/F'], capture_output=True)
                            killed = True
                        except (ValueError, IndexError):
                            pass
            
            if killed:
                return {'success': True, 'message': 'Qwen3 TTS service stopped'}
            else:
                return {'success': False, 'message': 'Qwen3 TTS service not found or already stopped'}
        else:  # Linux/Mac
            # Find and kill uvicorn processes
            result = subprocess.run(
                ["pkill", "-f", "uvicorn.*8000"],
                capture_output=True
            )
            if result.returncode == 0:
                return {'success': True, 'message': 'Qwen3 TTS service stopped'}
            else:
                return {'success': False, 'message': 'Qwen3 TTS service not found or already stopped'}
                
    except Exception as e:
        return {'success': False, 'message': f'Error stopping Qwen3 TTS service: {str(e)}'}

# --- Process Management Functions ---

def run_builder_process(command, cwd, process_type):
    """Runs a builder script as a subprocess and streams output to its dedicated queue."""
    global active_processes
    process_info = active_processes.get(process_type)
    if not process_info:
        print(f"Error: Process info not found for {process_type}")
        return

    output_queue = process_info['output_queue']
    process = None
    try:
        # Add PYTHONUNBUFFERED to force immediate output
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        process = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=0, universal_newlines=True, env=env)
        process_info['current_process'] = process
        process_info['running'] = True

        full_output_buffer = [] # Buffer to store all output lines
        start_time = datetime.datetime.now() # Capture start time

        # Read output line by line and put into queue and buffer
        for line in iter(process.stdout.readline, ''):
            output_queue.put(line)
            full_output_buffer.append(line)

        process.wait()

        end_time = datetime.datetime.now() # Capture end time
        calculated_duration = (end_time - start_time).total_seconds()

        total_duration = None
        # Try to parse duration from script output if available, otherwise use calculated
        full_output_str = "".join(full_output_buffer)
        duration_match = re.search(r"Total Duration: (\d+\.\d+) seconds", full_output_str)
        if duration_match:
            total_duration = float(duration_match.group(1))
        else:
            total_duration = calculated_duration # Fallback to calculated duration

        process_info['total_duration'] = total_duration # Store in process_info

        if process.returncode == 0:
            # Send a single complete message with all info
            final_output_files = []
            if process_type == 'script_builder':
                final_output_files = find_output_files(cwd)
            elif process_type == 'podcast_builder':
                # Find the most recent video file in outputs/final
                final_dir = os.path.join(cwd, 'outputs', 'final')
                if os.path.exists(final_dir):
                    try:
                        video_files = [f for f in os.listdir(final_dir) if f.endswith('.mp4')]
                        if video_files:
                            # Get the most recent video file
                            video_files.sort(key=lambda x: os.path.getmtime(os.path.join(final_dir, x)), reverse=True)
                            latest_video = video_files[0]
                            final_output_files.append(f"final/{latest_video}")
                    except OSError as e:
                        print(f"Error finding podcast output files: {e}")

            output_queue.put(json.dumps({
                'type': 'complete',
                'status': 'success',
                'message': f"--- {process_type.replace('_', ' ').title()} Complete ---",
                'output_files': final_output_files,
                'total_duration': total_duration
            }))
        else:
            # Send a single error message with all info
            output_queue.put(json.dumps({
                'type': 'complete', # Still send 'complete' type for frontend to close modal
                'status': 'error',
                'message': f"--- {process_type.replace('_', ' ').title()} Failed (Exit Code {process.returncode}) ---",
                'total_duration': total_duration # Still provide duration even on failure
            }))

    except FileNotFoundError:
        output_queue.put(json.dumps({
            'type': 'complete',
            'status': 'error',
            'message': f"Error: python or {process_type}.py not found. Ensure Python is in your PATH and the script exists."
        }))
    except Exception as e:
        output_queue.put(json.dumps({
            'type': 'complete',
            'status': 'error',
            'message': f"An unexpected error occurred during {process_type} execution: {e}",
            'traceback': traceback.format_exc()
        }))
    finally:
        output_queue.put(None) # Sentinel value
        process_info['running'] = False
        process_info['current_process'] = None

# --- Routes ---

@control_panel_app.route('/')
def index():
    """Render the main control panel dashboard."""
    return render_template('main_dashboard.html')

@control_panel_app.route('/script_builder')
def script_builder_form():
    """Render the script builder form."""
    llm_settings = load_llm_settings()
    available_models = list(llm_settings.keys()) if llm_settings else []
    return render_template('script_builder_form.html', llm_models=available_models)

@control_panel_app.route('/podcast_builder')
def podcast_builder_form():
    """Render the podcast builder form."""
    return render_template('podcast_builder_form.html')

@control_panel_app.route('/get_available_scripts', methods=['GET'])
def get_available_scripts():
    """Return available script files from outputs/scripts directory."""
    scripts_dir = os.path.join(control_panel_app.config['OUTPUT_FOLDER'], 'scripts')
    available_scripts = []
    
    if os.path.exists(scripts_dir):
        try:
            for file in os.listdir(scripts_dir):
                if file.endswith('.txt'):
                    file_path = os.path.join(scripts_dir, file)
                    file_stats = os.stat(file_path)
                    
                    # Detect if this is a single speaker script
                    is_single_speaker = detect_single_speaker_script(file_path)
                    
                    available_scripts.append({
                        'filename': file,
                        'path': f"scripts/{file}",
                        'modified': datetime.datetime.fromtimestamp(file_stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                        'size': file_stats.st_size,
                        'single_speaker': is_single_speaker
                    })
            # Sort by modification date, newest first
            available_scripts.sort(key=lambda x: x['modified'], reverse=True)
        except OSError as e:
            print(f"Error listing scripts directory: {e}")
    
    return jsonify({"scripts": available_scripts})

@control_panel_app.route('/api/podcasts', methods=['GET'])
def get_podcasts():
    """Scans the archive directory for podcast projects and returns them."""
    archive_dir = control_panel_app.config['ARCHIVE_DIR']
    podcasts = []
    if os.path.exists(archive_dir):
        for folder_name in os.listdir(archive_dir):
            folder_path = os.path.join(archive_dir, folder_name)
            if os.path.isdir(folder_path):
                for file_name in os.listdir(folder_path):
                    if file_name.endswith('.json'):
                        podcasts.append({
                            'name': folder_name,
                            'json_path': os.path.join(folder_path, file_name)
                        })
                        break # Found json, move to next folder
    return jsonify(podcasts)

def detect_single_speaker_script(script_path):
    """
    Detects if a script file contains only Host speakers (single speaker mode).
    Returns True if only Host lines are found, False if Guest lines are also present.
    """
    try:
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for Host and Guest lines
        has_host = bool(re.search(r'^Host:', content, re.MULTILINE))
        has_guest = bool(re.search(r'^Guest:', content, re.MULTILINE))
        
        # Single speaker if has Host but no Guest
        return has_host and not has_guest
    except Exception as e:
        print(f"Error reading script file {script_path}: {e}")
        return False

@control_panel_app.route('/settings')
def settings_page():
    """Render the settings page."""
    api_keys = load_api_keys()
    llm_settings = load_llm_settings()
    return render_template('settings.html', api_keys=api_keys, llm_settings=llm_settings)

@control_panel_app.route('/get_settings', methods=['GET'])
def get_settings():
    """Return API keys and LLM settings as JSON."""
    api_keys = load_api_keys()
    llm_settings = load_llm_settings()
    return jsonify({"api_keys": api_keys, "llm_settings": llm_settings})

@control_panel_app.route('/get_llm_models', methods=['GET'])
def get_llm_models():
    """Return LLM model keys as JSON for dropdowns."""
    llm_settings = load_llm_settings()
    available_models = list(llm_settings.keys()) if llm_settings else []
    return jsonify({"llm_models": available_models})

@control_panel_app.route('/history')
def history_page():
    """Render the history page and list generated outputs."""
    all_output_files = []
    base_output_folder = control_panel_app.config['OUTPUT_FOLDER']

    # Define specific subdirectories for videos and scripts
    video_output_dir = os.path.join(base_output_folder, 'final')
    script_output_dir = os.path.join(base_output_folder, 'scripts')

    # Ensure these directories exist before trying to list
    os.makedirs(video_output_dir, exist_ok=True)
    os.makedirs(script_output_dir, exist_ok=True)

    # Collect video files from outputs/final
    if os.path.exists(video_output_dir):
        for file in os.listdir(video_output_dir):
            if file.endswith('.mp4'):
                full_path = os.path.join(video_output_dir, file)
                relative_path = os.path.relpath(full_path, base_output_folder)
                all_output_files.append({
                    'name': file,
                    'path': relative_path,
                    'size': os.path.getsize(full_path),
                    'modified': datetime.datetime.fromtimestamp(os.path.getmtime(full_path)).strftime('%Y-%m-%d %H:%M:%S'),
                    'type': 'video'
                })

    # Collect script files from outputs/scripts
    if os.path.exists(script_output_dir):
        for file in os.listdir(script_output_dir):
            if file.endswith('.txt'):
                full_path = os.path.join(script_output_dir, file)
                relative_path = os.path.relpath(full_path, base_output_folder)
                all_output_files.append({
                    'name': file,
                    'path': relative_path,
                    'size': os.path.getsize(full_path),
                    'modified': datetime.datetime.fromtimestamp(os.path.getmtime(full_path)).strftime('%Y-%m-%d %H:%M:%S'),
                    'type': 'script'
                })

    # Sort by modification date, newest first
    all_output_files.sort(key=lambda x: x['modified'], reverse=True)
    return render_template('history.html', output_files=all_output_files)

@control_panel_app.route('/generate_script', methods=['POST'])
def generate_script():
    """Handle script generation requests and start the process."""
    process_type = 'script_builder'
    if active_processes.get(process_type, {}).get('running'):
        return jsonify({"status": "error", "message": f"A {process_type.replace('_', ' ')} process is already running."}), 409

    # Initialize process info if not exists
    if process_type not in active_processes:
        active_processes[process_type] = {
            'output_queue': queue.Queue(),
            'process_thread': None,
            'current_process': None,
            'running': False,
            'final_output_files': []
        }
    
    data = request.form
    uploaded_files = request.files

    script_path = os.path.join(os.path.dirname(__file__), 'script_builder.py')
    command = ['python', script_path]

    arg_map = {
        'topic': '--topic', 'keywords': '--keywords', 'guidance': '--guidance',
        'api': '--api', 'llm-model': '--llm-model', 'max-web-results': '--max-web-results',
        'max-reddit-results': '--max-reddit-results', 'max-reddit-comments': '--max-reddit-comments',
        'per-keyword-results': '--per-keyword-results', 'score-threshold': '--score-threshold',
        'ai-timeout': '--ai-timeout', 'ai-retries': '--ai-retries',
    }
    for field, arg in arg_map.items():
        value = data.get(field)
        if value:
            command.extend([arg, value])

    boolean_flags = {
        'combine-keywords': '--combine-keywords', 'no-search': '--no-search',
        'reference-docs-summarize': '--reference-docs-summarize', 'skip_refinement': '--skip-refinement',
        'no-reddit': '--no-reddit', 'report': '--report', 'youtube-description': '--youtube-description',
        'single-speaker': '--single-speaker',
    }
    for field, arg in boolean_flags.items():
        if data.get(field) == 'on':
            command.append(arg)

    uploaded_ref_docs_paths = []
    if 'reference-docs' in uploaded_files:
        for file in uploaded_files.getlist('reference-docs'):
            if file.filename:
                filepath = os.path.join(control_panel_app.config['UPLOAD_FOLDER'], file.filename)
                file.save(filepath)
                uploaded_ref_docs_paths.append(filepath)
    if uploaded_ref_docs_paths:
        command.extend(['--reference-docs', ','.join(uploaded_ref_docs_paths)])

    if 'direct-articles' in uploaded_files:
        file = uploaded_files['direct-articles']
        if file.filename:
            filepath = os.path.join(control_panel_app.config['UPLOAD_FOLDER'], file.filename)
            file.save(filepath)
            command.extend(['--direct-articles', filepath])

    uploaded_folder_files = uploaded_files.getlist('reference-docs-folder')
    if uploaded_folder_files:
         first_file = uploaded_folder_files[0]
         if first_file.filename:
              relative_folder_path = os.path.dirname(first_file.filename)
              if relative_folder_path:
                   folder_path_in_uploads = os.path.join(control_panel_app.config['UPLOAD_FOLDER'], relative_folder_path)
                   for file in uploaded_folder_files:
                        if file.filename:
                             filepath = os.path.join(control_panel_app.config['UPLOAD_FOLDER'], file.filename)
                             os.makedirs(os.path.dirname(filepath), exist_ok=True)
                             file.save(filepath)
                   command.extend(['--reference-docs-folder', folder_path_in_uploads])

    print(f"Executing command for {process_type}: {' '.join(command)}")

    # Clear previous output
    while not active_processes[process_type]['output_queue'].empty():
        try:
            active_processes[process_type]['output_queue'].get_nowait()
        except queue.Empty:
            pass
    active_processes[process_type]['final_output_files'] = []

    process_thread = threading.Thread(target=run_builder_process, args=(command, os.path.dirname(__file__), process_type))
    active_processes[process_type]['process_thread'] = process_thread
    process_thread.start()

    return jsonify({"status": "processing", "message": f"{process_type.replace('_', ' ').title()} started. Please wait for progress."})

@control_panel_app.route('/generate_ai_suggestions', methods=['POST'])
def generate_ai_suggestions():
    """
    Generates topic, keywords, and guidance using AI based on user description.
    """
    data = request.json
    description = data.get('description')
    llm_model_key = data.get('llm_model')

    if not description or not llm_model_key:
        return jsonify({"status": "error", "message": "Description and LLM model are required."}), 400

    llm_settings = load_llm_settings()
    selected_model_config = llm_settings.get(llm_model_key)

    if not selected_model_config:
        return jsonify({"status": "error", "message": f"LLM model '{llm_model_key}' not found in settings."}), 404

    # Prepare config for call_ai_api
    ai_config = {
        "selected_model_config": selected_model_config,
        "final_model_key": llm_model_key # Pass the key for logging/error messages
    }

    prompt_template = """
    Based on the following podcast description, please generate a concise Topic, three Key Phrases for searching (comma-separated), and detailed Guidance for the podcast script.
    Ensure each output is enclosed in specific XML-like tags:
    <Topic_Idea>Your generated topic here</Topic_Idea>
    <Key_Phrases>keyword1, keyword2, keyword3</Key_Phrases>
    <Guidance_Idea>Your detailed guidance here</Guidance_Idea>

    Podcast Description:
    {description}
    """
    prompt = prompt_template.format(description=description)

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        print(f"Attempt {attempt} to generate AI suggestions for '{llm_model_key}'...")
        raw_response, cleaned_response = call_ai_api(prompt, ai_config, tool_name="AI Suggestions")

        if cleaned_response:
            topic_match = re.search(r"<Topic_Idea>(.*?)</Topic_Idea>", cleaned_response, re.DOTALL)
            keywords_match = re.search(r"<Key_Phrases>(.*?)</Key_Phrases>", cleaned_response, re.DOTALL)
            guidance_match = re.search(r"<Guidance_Idea>(.*?)</Guidance_Idea>", cleaned_response, re.DOTALL)

            topic = topic_match.group(1).strip() if topic_match else None
            keywords = keywords_match.group(1).strip() if keywords_match else None
            guidance = guidance_match.group(1).strip() if guidance_match else None

            if topic and keywords and guidance:
                return jsonify({
                    "status": "success",
                    "topic": topic,
                    "keywords": keywords,
                    "guidance": guidance
                })
            else:
                print(f"Attempt {attempt} failed to extract all required fields. Retrying...")
        else:
            print(f"Attempt {attempt} received no response or an error from AI. Retrying...")

    return jsonify({"status": "error", "message": f"Failed to generate AI suggestions after {max_attempts} attempts. Please try again or refine your description."}), 500

@control_panel_app.route('/generate_podcast_video', methods=['POST'])
def generate_podcast_video():
    """Handle podcast generation requests and start the process."""
    process_type = 'podcast_builder'
    if active_processes.get(process_type, {}).get('running'):
        return jsonify({"status": "error", "message": f"A {process_type.replace('_', ' ')} process is already running."}), 409

    # Initialize process info if not exists
    if process_type not in active_processes:
        active_processes[process_type] = {
            'output_queue': queue.Queue(),
            'process_thread': None,
            'current_process': None,
            'running': False,
            'final_output_files': []
        }

    data = request.form
    uploaded_files = request.files

    script_path = os.path.join(os.path.dirname(__file__), 'podcast_builder.py')
    command = ['python', script_path]
    command.append('--dev')

    # Check if resuming from JSON or starting new
    resume_json_path = data.get('resume_from_json')

    if resume_json_path:
        if os.path.exists(resume_json_path):
            command.extend(['--resume-from-json', resume_json_path])
        else:
            return jsonify({"status": "error", "message": f"Selected JSON file not found: {resume_json_path}"}), 400
    else:
        # This block handles new podcast generation, so script validation is required.
        selected_script = data.get('script_select')
        script_file = uploaded_files.get('script_file')
        
        script_to_use = None
        if selected_script and selected_script != 'custom' and selected_script != '':
            # Using a predefined script from outputs/scripts
            script_path_from_select = os.path.join(control_panel_app.config['OUTPUT_FOLDER'], selected_script)
            if os.path.exists(script_path_from_select):
                script_to_use = script_path_from_select
            else:
                return jsonify({"status": "error", "message": f"Selected script file not found: {selected_script}"}), 400
        elif script_file and script_file.filename:
            # Using uploaded custom script file
            filepath = os.path.join(control_panel_app.config['UPLOAD_FOLDER'], script_file.filename)
            script_file.save(filepath)
            script_to_use = filepath
        
        if script_to_use:
            command.extend(['--script', script_to_use])
        else:
            return jsonify({"status": "error", "message": "Please select a script from the dropdown or choose 'Custom' to upload a file."}), 400

    # TTS Provider
    tts_provider = data.get('tts_provider', 'qwen3')
    command.extend(['--tts-provider', tts_provider])
    
    # Handle Host Voice
    host_voice_mode = data.get('host_voice_mode', 'preset')
    if host_voice_mode == 'preset':
        host_voice = data.get('host_voice')
        if host_voice:
            command.extend(['--host-voice', host_voice])
    elif host_voice_mode == 'clone':
        # Handle voice clone file upload for host
        host_sample = uploaded_files.get('host_voice_sample')
        if host_sample and host_sample.filename:
            host_sample_path = os.path.join(control_panel_app.config['UPLOAD_FOLDER'], f"host_{host_sample.filename}")
            host_sample.save(host_sample_path)
            command.extend(['--host-voice-sample', host_sample_path])
            host_sample_text = data.get('host_voice_sample_text')
            if host_sample_text:
                command.extend(['--host-voice-text', host_sample_text])
        else:
            return jsonify({"status": "error", "message": "Please upload a voice sample file for host voice cloning"}), 400
    elif host_voice_mode == 'saved':
        host_saved_id = data.get('host_saved_voice_id')
        if host_saved_id:
            command.extend(['--host-voice', host_saved_id])
        else:
            return jsonify({"status": "error", "message": "Please enter a saved voice ID for host"}), 400
    
    # Handle Guest Voice
    guest_voice_mode = data.get('guest_voice_mode', 'preset')
    if guest_voice_mode == 'preset':
        guest_voice = data.get('guest_voice')
        if guest_voice:
            command.extend(['--guest-voice', guest_voice])
    elif guest_voice_mode == 'clone':
        # Handle voice clone file upload for guest
        guest_sample = uploaded_files.get('guest_voice_sample')
        if guest_sample and guest_sample.filename:
            guest_sample_path = os.path.join(control_panel_app.config['UPLOAD_FOLDER'], f"guest_{guest_sample.filename}")
            guest_sample.save(guest_sample_path)
            command.extend(['--guest-voice-sample', guest_sample_path])
            guest_sample_text = data.get('guest_voice_sample_text')
            if guest_sample_text:
                command.extend(['--guest-voice-text', guest_sample_text])
        else:
            return jsonify({"status": "error", "message": "Please upload a voice sample file for guest voice cloning"}), 400
    elif guest_voice_mode == 'saved':
        guest_saved_id = data.get('guest_saved_voice_id')
        if guest_saved_id:
            command.extend(['--guest-voice', guest_saved_id])
        else:
            return jsonify({"status": "error", "message": "Please enter a saved voice ID for guest"}), 400
    
    arg_map = {
        'silence': '--silence', 'speed': '--speed', 'port': '--port', 'api_host': '--api-host',
        'output_filename': '--output', 'video_resolution': '--video-resolution',
        'video_fps': '--video-fps', 'video_character_scale': '--video-character-scale',
        'video_fade': '--video-fade', 'video_intermediate_preset': '--video-intermediate-preset',
        'video_intermediate_crf': '--video-intermediate-crf', 'video_final_audio_bitrate': '--video-final-audio-bitrate',
        'video_workers': '--video-workers', 'tts_max_retries': '--tts-max-retries', 'tts_timeout': '--tts-timeout',
    }
    for field, arg in arg_map.items():
        value = data.get(field)
        if value:
            if field in ['silence', 'speed', 'port', 'video_fps', 'video_character_scale', 'video_fade', 'video_intermediate_crf', 'video_workers', 'tts_max_retries', 'tts_timeout']:
                try:
                    if value.strip() != '':
                        command.extend([arg, str(float(value) if '.' in value else int(value))])
                except ValueError:
                    return jsonify({"status": "error", "message": f"Invalid numeric value for {field}: {value}"}), 400
            else:
                command.extend([arg, value])

    boolean_flags = {
        'guest_breakup': '--guest-breakup', 'video_keep_temp': '--video-keep-temp',
    }
    for field, arg in boolean_flags.items():
        if data.get(field) == 'on':
            command.append(arg)

    print(f"Executing command for {process_type}: {' '.join(command)}")

    while not active_processes[process_type]['output_queue'].empty():
        try:
            active_processes[process_type]['output_queue'].get_nowait()
        except queue.Empty:
            pass
    active_processes[process_type]['final_output_files'] = []

    process_thread = threading.Thread(target=run_builder_process, args=(command, os.path.dirname(__file__), process_type))
    active_processes[process_type]['process_thread'] = process_thread
    process_thread.start()

    return jsonify({"status": "processing", "message": f"{process_type.replace('_', ' ').title()} started. Please wait for progress."})

@control_panel_app.route('/stream_output')
def stream_output():
    """Streams output from a specified subprocess using Server-Sent Events."""
    process_type = request.args.get('type')
    if not process_type or process_type not in active_processes:
        return Response("data: {'type': 'error', 'content': 'Invalid process type specified.'}\n\n", mimetype='text/event-stream')

    process_info = active_processes[process_type]
    output_queue = process_info['output_queue']

    def generate():
        while process_info['running'] or not output_queue.empty():
            try:
                line = output_queue.get(timeout=1)
                if line is None:
                    break

                # Specific parsing for podcast_builder output
                if process_type == 'podcast_builder':
                    total_segments_match = re.search(r"Found (\d+) valid dialogue segments.", line)
                    if total_segments_match:
                        yield f"data: {json.dumps({'type': 'total_segments', 'count': int(total_segments_match.group(1))})}\n\n"
                        continue

                    segment_progress_match = re.search(r"Segment (\d+) \(Line \d+\):", line)
                    if segment_progress_match:
                        yield f"data: {json.dumps({'type': 'segment_progress', 'current': int(segment_progress_match.group(1))})}\n\n"
                        continue
                    
                    # Also catch the processing message that appears during audio generation
                    processing_match = re.search(r"Processing (\d+) segments for final JSON", line)
                    if processing_match:
                        yield f"data: {json.dumps({'type': 'processing_update', 'message': 'Finalizing audio segments...'})}\n\n"
                        continue
                    
                    if "Entering development mode for segment review..." in line:
                        yield f"data: {json.dumps({'type': 'gui_active', 'content': 'Pygame GUI active, awaiting user interaction...'})}\n\n"
                        continue

                    video_path_match = re.search(r"Video generation process initiated for (.+?\.mp4)\.", line)
                    if video_path_match:
                        full_path = video_path_match.group(1)
                        relative_path = os.path.relpath(full_path, control_panel_app.config['OUTPUT_FOLDER'])
                        process_info['final_output_files'].append(relative_path)
                        yield f"data: {json.dumps({'type': 'video_ready', 'path': relative_path})}\n\n"
                        continue

                # Attempt to parse any line as a JSON event
                try:
                    event_dict = json.loads(line.strip())
                    if isinstance(event_dict, dict) and 'type' in event_dict:
                        yield f"data: {json.dumps(event_dict)}\n\n"
                        continue
                except json.JSONDecodeError:
                    pass  # Not a JSON event, continue to output

                yield f"data: {json.dumps({'type': 'output', 'content': line})}\n\n"
            except queue.Empty:
                yield "data: {}\n\n"
            except Exception as e:
                 print(f"Error streaming output for {process_type}: {e}")
                 yield f"data: {json.dumps({'type': 'error', 'content': f'Streaming error: {e}'})}\n\n"
                 break
 
 
    response = Response(generate(), mimetype='text/event-stream')
    response.headers['X-Accel-Buffering'] = 'no'
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['Connection'] = 'keep-alive'
    return response

@control_panel_app.route('/outputs/<path:filename>')
def serve_output(filename):
    """Serve generated output files from the outputs directory."""
    try:
        # Try serving from the main outputs folder first
        return send_from_directory(control_panel_app.config['OUTPUT_FOLDER'], filename)
    except FileNotFoundError:
        # If not found, try serving from the archive folder
        try:
            return send_from_directory(control_panel_app.config['ARCHIVE_DIR'], filename)
        except FileNotFoundError:
            return "Output file not found.", 404

@control_panel_app.route('/stop_process', methods=['POST'])
def stop_process():
    """Stops the currently running process of a specified type."""
    process_type = request.json.get('type')
    if not process_type or process_type not in active_processes:
        return jsonify({"status": "error", "message": "Invalid process type specified."}), 400

    process_info = active_processes[process_type]
    current_process = process_info.get('current_process')
    process_running = process_info.get('running')

    if current_process and process_running:
        try:
            current_process.terminate()
            current_process.wait(timeout=5)
            process_info['running'] = False
            process_info['current_process'] = None
            return jsonify({"status": "success", "message": f"{process_type.replace('_', ' ').title()} process stopped."})
        except Exception as e:
            return jsonify({"status": "error", "message": f"Error stopping {process_type.replace('_', ' ')} process: {e}"}), 500
    else:
        return jsonify({"status": "info", "message": f"No {process_type.replace('_', ' ')} process is currently running."})

@control_panel_app.route('/save_settings', methods=['POST'])
def save_settings_route():
    """Handle saving API keys and LLM settings."""
    data = request.json
    api_keys_data = data.get('apiKeys', {})
    llm_settings_data = data.get('llmSettings', {})

    api_success, api_message = save_api_keys(api_keys_data)
    llm_success, llm_message = save_llm_settings(llm_settings_data)

    if api_success and llm_success:
        return jsonify({"status": "success", "message": "Settings saved successfully."})
    else:
        error_message = ""
        if not api_success:
            error_message += f"API Keys Save Failed: {api_message} "
        if not llm_success:
            error_message += f"LLM Settings Save Failed: {llm_message}"
        return jsonify({"status": "error", "message": error_message.strip()}), 500

@control_panel_app.route('/docker/status', methods=['GET'])
def docker_status():
    """Get the current status of Orpheus-FastAPI Docker containers."""
    status = check_docker_status()
    return jsonify(status)

@control_panel_app.route('/docker/start', methods=['POST'])
def docker_start():
    """Start Orpheus-FastAPI Docker containers."""
    result = start_docker_containers()
    if result['success']:
        return jsonify({"status": "success", "message": result['message']})
    else:
        return jsonify({"status": "error", "message": result['message']}), 500

@control_panel_app.route('/docker/stop', methods=['POST'])
def docker_stop():
    """Stop Orpheus-FastAPI Docker containers."""
    result = stop_docker_containers()
    if result['success']:
        return jsonify({"status": "success", "message": result['message']})
    else:
        return jsonify({"status": "error", "message": result['message']}), 500

@control_panel_app.route('/tts/status', methods=['GET'])
def tts_status():
    """Get the current status of the TTS service (Qwen3 or check Docker for Orpheus)."""
    tts_provider = os.getenv('TTS_PROVIDER', 'qwen3').lower()
    
    if tts_provider == 'qwen3':
        status = check_qwen3_status()
        status['provider'] = 'qwen3'
        return jsonify(status)
    else:
        # For Orpheus, check Docker status
        status = check_docker_status()
        status['provider'] = 'orpheus'
        return jsonify(status)

@control_panel_app.route('/tts/start', methods=['POST'])
def tts_start():
    """Start the TTS service based on configured provider."""
    tts_provider = os.getenv('TTS_PROVIDER', 'qwen3').lower()
    
    if tts_provider == 'qwen3':
        result = start_qwen3_service()
        if result['success']:
            return jsonify({"status": "success", "message": result['message']})
        else:
            return jsonify({"status": "error", "message": result['message']}), 500
    else:
        # For Orpheus, start Docker containers
        result = start_docker_containers()
        if result['success']:
            return jsonify({"status": "success", "message": result['message']})
        else:
            return jsonify({"status": "error", "message": result['message']}), 500

@control_panel_app.route('/tts/models/download/<model_id>', methods=['POST'])
def download_tts_model(model_id):
    """Download/load a specific TTS model."""
    qwen3_port = os.getenv('QWEN3_PORT', '8000')
    
    try:
        response = requests.post(
            f"http://127.0.0.1:{qwen3_port}/v1/models/{model_id}/load",
            timeout=300  # 5 minutes for download
        )
        if response.status_code == 200:
            return jsonify({"status": "success", "message": f"Model {model_id} downloaded and loaded"})
        else:
            data = response.json() if response.text else {}
            return jsonify({"status": "error", "message": data.get('detail', f'Failed to download model: {response.status_code}')}), response.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"status": "error", "message": "Cannot connect to Qwen3 TTS API"}), 503
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@control_panel_app.route('/tts/stop', methods=['POST'])
def tts_stop():
    """Stop the TTS service based on configured provider."""
    tts_provider = os.getenv('TTS_PROVIDER', 'qwen3').lower()
    
    if tts_provider == 'qwen3':
        result = stop_qwen3_service()
        if result['success']:
            return jsonify({"status": "success", "message": result['message']})
        else:
            return jsonify({"status": "error", "message": result['message']}), 500
    else:
        # For Orpheus, stop Docker containers
        result = stop_docker_containers()
        if result['success']:
            return jsonify({"status": "success", "message": result['message']})
        else:
            return jsonify({"status": "error", "message": result['message']}), 500

if __name__ == '__main__':
    control_panel_app.run(debug=True, port=5000)
