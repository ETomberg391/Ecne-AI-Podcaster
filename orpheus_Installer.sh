#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e
# Treat unset variables as an error when substituting.
set -u
# Pipelines return the exit status of the last command to exit non-zero.
set -o pipefail

# --- Configuration ---
DEFAULT_INSTALL_DIR="orpheus_tts_setup"
DEFAULT_LLAMA_SERVER_PORT="8080"
DEFAULT_FASTAPI_PORT="5006"
MODEL_URL="https://huggingface.co/lex-au/Orpheus-3b-FT-Q8_0.gguf/resolve/main/Orpheus-3b-FT-Q8_0.gguf?download=true"
MODEL_FILENAME="Orpheus-3b-FT-Q8_0.gguf"
PYTHON_CMD="python3" # Change if your python 3 is just 'python'
PIP_CMD="pip3"     # Change if your pip 3 is just 'pip'
LLAMA_SERVER_EXE_NAME="llama-server" # Confirmed executable name
ORPHEUS_MAX_TOKENS="8192" # Default max tokens for llama.cpp server

# --- Helper Functions ---
print_info() {
    echo "INFO: $1"
}

print_warning() {
    echo "WARNING: $1"
}

print_error() {
    echo "ERROR: $1" >&2
    exit 1
}

check_command() {
    local cmd="$1"
    local install_suggestion="${2:-}" # Use default empty string if $2 is unset

    if ! command -v "$cmd" &> /dev/null; then
        local error_msg="Command '$cmd' not found."
        if [ -n "$install_suggestion" ]; then
            error_msg="$error_msg $install_suggestion"
        else
            error_msg="$error_msg Please install it first (e.g., using apt, yum, brew, pkg install, etc.)."
        fi
        print_error "$error_msg" # print_error already exits
    fi
}

# --- Main Script ---

echo "---------------------------------------------"
echo " Orpheus TTS GGUF Setup Script (V5 - Simplified Build) "
echo "---------------------------------------------"
# ... (rest of intro and prerequisite checks remain the same) ...
print_info "Checking prerequisites..."
check_command "git" "Please install git (e.g., sudo apt install git)"
check_command "docker" "Please install Docker (https://docs.docker.com/engine/install/)"
# Check for both docker compose syntaxes
if command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker-compose"
    print_info "Found 'docker-compose' (V1 syntax)."
elif docker compose version &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker compose"
    print_info "Found 'docker compose' (V2 syntax)."
else
    print_error "Docker Compose not found. Please install Docker Compose (V1 or V2). See: https://docs.docker.com/compose/install/"
fi

print_info "Core prerequisites met."

# --- Host Python Script Prerequisites ---
print_info "Checking prerequisites for host Python scripts (mainv3.py, orpheus_ttsv3.py)..."
check_command "${PYTHON_CMD}" "Please install Python 3 (e.g., sudo apt install python3)"
check_command "${PIP_CMD}" "Please install pip for Python 3 (e.g., sudo apt install python3-pip)"
check_command "ffmpeg" "Please install ffmpeg (e.g., sudo apt install ffmpeg)"

print_warning "Host scripts (mainv3.py, orpheus_ttsv3.py) may require additional system libraries."
print_warning "Please ensure the following are installed if you encounter errors running those scripts:"
print_warning "  - Tkinter: sudo apt install python3-tk (or equivalent)"
print_warning "  - libsndfile: sudo apt install libsndfile1 (or equivalent)"
print_warning "  - PortAudio: sudo apt install portaudio19-dev (or equivalent)"
print_warning "  - Selenium WebDriver: Requires a browser (e.g., Chrome) and the corresponding WebDriver (e.g., chromedriver) installed and in your system's PATH."


# --- Optional System Dependency Installation ---
print_info "Attempting to detect Linux distribution for optional dependency installation..."
OS_ID=""
PKG_MANAGER=""
INSTALL_CMD=""
UPDATE_CMD=""

if [ -f /etc/os-release ]; then
    # Freedesktop.org and systemd
    . /etc/os-release
    OS_ID=$ID
    print_info "Detected OS ID: $OS_ID"

    case "$OS_ID" in
        ubuntu|debian|linuxmint|pop|elementary|zorin) # Added pop, elementary, zorin, linuxmint explicitly
            PKG_MANAGER="apt"
            UPDATE_CMD="sudo apt update"
            INSTALL_CMD="sudo apt install -y"
            DEPS_TO_INSTALL="ffmpeg python3-tk libsndfile1 portaudio19-dev"
            ;;
        arch|manjaro|endeavouros|garuda) # Added endeavouros, garuda, manjaro explicitly
            PKG_MANAGER="pacman"
            UPDATE_CMD="sudo pacman -Sy"
            INSTALL_CMD="sudo pacman -S --noconfirm"
            # Arch often has slightly different package names
            DEPS_TO_INSTALL="ffmpeg tk libsndfile portaudio"
            ;;
        fedora|centos|rhel|rocky|almalinux) # Added rocky, almalinux explicitly
            # Check for dnf first, fallback to yum
            if command -v dnf &> /dev/null; then
                PKG_MANAGER="dnf"
                UPDATE_CMD="sudo dnf check-update" # check-update doesn't require sudo usually, but won't harm
                INSTALL_CMD="sudo dnf install -y"
            elif command -v yum &> /dev/null; then
                PKG_MANAGER="yum"
                UPDATE_CMD="sudo yum check-update"
                INSTALL_CMD="sudo yum install -y"
            fi
            if [ -n "$PKG_MANAGER" ]; then
                 # Fedora/CentOS package names (python3-tkinter is common)
                DEPS_TO_INSTALL="ffmpeg python3-tkinter libsndfile portaudio-devel"
            fi
            ;;
        opensuse*|sles) # Added openSUSE/SLES
             PKG_MANAGER="zypper"
             UPDATE_CMD="sudo zypper refresh"
             INSTALL_CMD="sudo zypper install -y"
             # openSUSE package names
             DEPS_TO_INSTALL="ffmpeg python3-tk libsndfile1 portaudio-devel" # Check these names
             ;;
        *)
            # Also check ID_LIKE from /etc/os-release as a fallback
            if [ -n "$ID_LIKE" ]; then
                print_info "Trying fallback detection based on ID_LIKE='$ID_LIKE'..."
                case "$ID_LIKE" in
                    *debian*) # Covers ubuntu, mint, pop etc.
                        PKG_MANAGER="apt"
                        UPDATE_CMD="sudo apt update"
                        INSTALL_CMD="sudo apt install -y"
                        DEPS_TO_INSTALL="ffmpeg python3-tk libsndfile1 portaudio19-dev"
                        ;;
                    *arch*) # Covers manjaro, endeavouros etc.
                        PKG_MANAGER="pacman"
                        UPDATE_CMD="sudo pacman -Sy"
                        INSTALL_CMD="sudo pacman -S --noconfirm"
                        DEPS_TO_INSTALL="ffmpeg tk libsndfile portaudio"
                        ;;
                    *fedora*) # Covers centos, rhel etc.
                        if command -v dnf &> /dev/null; then
                            PKG_MANAGER="dnf"
                            UPDATE_CMD="sudo dnf check-update"
                            INSTALL_CMD="sudo dnf install -y"
                        elif command -v yum &> /dev/null; then
                            PKG_MANAGER="yum"
                            UPDATE_CMD="sudo yum check-update"
                            INSTALL_CMD="sudo yum install -y"
                        fi
                        if [ -n "$PKG_MANAGER" ]; then
                            DEPS_TO_INSTALL="ffmpeg python3-tkinter libsndfile portaudio-devel"
                        fi
                        ;;
                    *suse*)
                         PKG_MANAGER="zypper"
                         UPDATE_CMD="sudo zypper refresh"
                         INSTALL_CMD="sudo zypper install -y"
                         DEPS_TO_INSTALL="ffmpeg python3-tk libsndfile1 portaudio-devel" # Check these names
                         ;;
                    *)
                        print_warning "Unsupported Linux distribution ($OS_ID) and ID_LIKE ($ID_LIKE) for automatic dependency installation."
                        PKG_MANAGER=""
                        ;;
                esac
            else
                 print_warning "Unsupported Linux distribution ($OS_ID) for automatic dependency installation."
                 PKG_MANAGER=""
            fi
            ;;
    esac
elif command -v lsb_release &> /dev/null; then
    # Fallback for older systems
    OS_ID=$(lsb_release -is | tr '[:upper:]' '[:lower:]')
    print_warning "Using fallback OS detection (lsb_release). May be less accurate."
    # Add cases for lsb_release output if needed, similar to above
else
    print_warning "Could not determine Linux distribution. Cannot attempt automatic dependency installation."
fi

if [ -n "$PKG_MANAGER" ] && [ -n "$INSTALL_CMD" ] && [ -n "$DEPS_TO_INSTALL" ]; then
    echo
    print_warning "The following system packages are recommended or required for host scripts:"
    print_warning "  $DEPS_TO_INSTALL"
    read -p "Do you want to attempt installing these using '$PKG_MANAGER'? (Requires sudo) [y/N]: " INSTALL_DEPS
    INSTALL_DEPS=$(echo "$INSTALL_DEPS" | tr '[:upper:]' '[:lower:]')

    if [[ "$INSTALL_DEPS" == "y" ]]; then
        print_info "Attempting to install dependencies using $PKG_MANAGER..."
        if [ -n "$UPDATE_CMD" ]; then
            print_info "Running package list update ($UPDATE_CMD)..."
            set +e # Don't exit if update fails, but warn
            $UPDATE_CMD
            if [ $? -ne 0 ]; then
                print_warning "Package list update failed. Installation might use outdated lists or fail."
            fi
            set -e
        fi
        print_info "Running installation ($INSTALL_CMD $DEPS_TO_INSTALL)..."
        set +e # Don't exit immediately if install fails
        $INSTALL_CMD $DEPS_TO_INSTALL
        INSTALL_EXIT_CODE=$?
        set -e

        if [ $INSTALL_EXIT_CODE -eq 0 ]; then
            print_info "System dependency installation attempt finished successfully."
        else
            print_error "System dependency installation attempt failed (Exit Code: $INSTALL_EXIT_CODE). Please install them manually: $DEPS_TO_INSTALL"
        fi
    else
        print_info "Skipping automatic system dependency installation. Please ensure they are installed manually if needed."
    fi
fi

echo

# --- Get User Input ---
read -p "Enter installation directory [${DEFAULT_INSTALL_DIR}]: " INSTALL_DIR
INSTALL_DIR=${INSTALL_DIR:-$DEFAULT_INSTALL_DIR}

# Sudo check (still relevant for directory creation/permissions)
if [ "$(id -u)" != "0" ] && [ -e "$INSTALL_DIR" ] && [ ! -w "$INSTALL_DIR" ]; then
    print_error "Installation directory '$INSTALL_DIR' exists and is not writable by the current user. Please choose a different directory or run with sudo (not recommended)."
fi
if [ "$(id -u)" == "0" ]; then
    print_warning "Running with sudo. Installation will be owned by root."
    read -p "Are you sure you want to continue with sudo? (y/N): " CONFIRM_SUDO
    CONFIRM_SUDO=$(echo "$CONFIRM_SUDO" | tr '[:upper:]' '[:lower:]')
    if [[ "$CONFIRM_SUDO" != "y" ]]; then
        echo "Aborting."
        exit 1
    fi
fi

# Check for GPU and NVIDIA Container Toolkit
USE_GPU="n" # Default to no GPU usage info needed for Docker compose unless checked
if command -v nvidia-smi &> /dev/null; then
    print_info "Nvidia GPU detected."
    USE_GPU="y" # Mark that GPU is present
    print_info "Checking for NVIDIA Container Toolkit (required for Docker GPU access)..."
    # Simple check: look for the runtime command.
    if ! command -v nvidia-container-runtime &> /dev/null && ! command -v nvidia-container-toolkit &> /dev/null; then
         print_warning "NVIDIA Container Toolkit (nvidia-container-runtime or nvidia-container-toolkit command) not found."
         print_warning "Docker compose requires this to access the GPU."
         print_warning "See: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html"
         read -p "Continue anyway? (docker compose will likely fail to use the GPU) [y/N]: " CONFIRM_NO_NVIDIA_TOOLKIT
         CONFIRM_NO_NVIDIA_TOOLKIT=$(echo "$CONFIRM_NO_NVIDIA_TOOLKIT" | tr '[:upper:]' '[:lower:]')
         if [[ "$CONFIRM_NO_NVIDIA_TOOLKIT" != "y" ]]; then
             echo "Aborting."
             exit 1
         fi
    else
        print_info "NVIDIA Container Toolkit command found. Docker GPU support should be available."
    fi
fi

# --- Create Directories ---
print_info "Ensuring installation directory exists: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"
INSTALL_DIR_ABS=$(pwd) # Get absolute path

# Only create the Orpheus-FastAPI directory, as others are handled by docker-compose
mkdir -p Orpheus-FastAPI

# --- Get Orpheus-FastAPI Source Code ---
print_info "Ensuring Orpheus-FastAPI source code is present..."
cd "$INSTALL_DIR_ABS/Orpheus-FastAPI"
FASTAPI_DIR=$(pwd) # Store path for final instructions

if [ -d ".git" ]; then
    print_warning "Orpheus-FastAPI directory already exists, pulling latest."
    set +e
    git reset --hard HEAD > /dev/null 2>&1
    git pull origin main > /dev/null 2>&1
    if [ $? -ne 0 ]; then
      print_warning "Git pull failed for Orpheus-FastAPI. Proceeding with existing files."
    else
      print_info "Successfully pulled latest changes for Orpheus-FastAPI."
    fi
    set -e
else
    # Directory exists, but it's not a git repository.
    # Check if it's empty before attempting to clone.
    if [ -z "$(ls -A .)" ]; then
        # Directory is empty, safe to clone
        print_info "Cloning Orpheus-FastAPI repository..."
        git clone https://github.com/Lex-au/Orpheus-FastAPI.git .
    else

# --- Setup Host Python Environment (for mainv3.py, orpheus_ttsv3.py) ---
print_info "Setting up Python virtual environment for host scripts (mainv3.py, orpheus_ttsv3.py)..."
HOST_VENV_DIR="host_venv"
cd "$INSTALL_DIR_ABS" # Ensure we are in the base installation directory

if [ ! -d "$HOST_VENV_DIR" ]; then
    print_info "Creating Python virtual environment '$HOST_VENV_DIR' for host scripts..."
    $PYTHON_CMD -m venv "$HOST_VENV_DIR"
else
    print_warning "Host virtual environment '$HOST_VENV_DIR' already exists. Skipping creation."
    print_warning "If you encounter issues, remove the '$HOST_VENV_DIR' directory and re-run the script."
fi

print_info "Activating host virtual environment and installing dependencies from requirements_host.txt..."
source "$HOST_VENV_DIR/bin/activate"

# Upgrade pip within the venv
print_info "Upgrading pip in host venv..."
$PIP_CMD install --upgrade pip

# Install dependencies
if [ -f "../requirements_host.txt" ]; then # Check relative path from INSTALL_DIR
    print_info "Installing host dependencies from ../requirements_host.txt..."
    $PIP_CMD install -r "../requirements_host.txt"
    # Download NLTK data (punkt) after installation
    print_info "Downloading NLTK 'punkt' tokenizer data (required for sentence splitting)..."
    $PYTHON_CMD -m nltk.downloader punkt
else
    print_error "Could not find requirements_host.txt in the parent directory. Cannot install host dependencies."
fi

deactivate
print_info "Host Python environment setup complete."
cd "$INSTALL_DIR_ABS" # Go back to base install dir just in case

        # Directory is not empty, assume files are present from previous attempt/manual copy
        print_warning "Directory '.' exists and is not empty, but not a git repository. Skipping clone and assuming files are present."
        print_warning "The docker compose command will use the existing files in this directory."
    fi
fi
print_info "Orpheus-FastAPI source code is ready."
    # Copy .env.example to .env if .env doesn't exist
    if [ ! -f ".env" ]; then
        print_info "Copying .env.example to .env..."
        cp .env.example .env
    else
        print_warning ".env file already exists. Skipping copy from .env.example."
        print_warning "Please review your existing .env file manually: $FASTAPI_DIR/.env"
    fi
cd "$INSTALL_DIR_ABS" # Go back to base install dir

# --- Final Instructions ---
echo
echo "---------------------------------------------"
echo " Setup Complete! "
echo "---------------------------------------------"
echo
echo "The necessary source code for Orpheus-FastAPI has been cloned/updated into:"
echo "  $FASTAPI_DIR"
echo
echo "Next Steps:"
echo
echo "1. Navigate to the Orpheus-FastAPI directory:"
echo "   cd \"$FASTAPI_DIR\""
echo
echo "2. Start the services using Docker Compose:"
echo "   $DOCKER_COMPOSE_CMD -f docker-compose-gpu.yml up"
echo "   (Add '-d' to run in detached mode: $DOCKER_COMPOSE_CMD -f docker-compose-gpu.yml up -d)"
echo
echo "3. Access the Web UI:"
echo "   Once the containers are running, access the UI in your browser at:"
# Use the default port from the compose file, as we didn't ask the user
# Assuming the compose file maps to port 5005 on the host by default
echo "   http://127.0.0.1:5005"
echo
echo "4. To stop the services:"
echo "   Press Ctrl+C in the terminal where compose is running, or if detached:"
echo "   $DOCKER_COMPOSE_CMD -f docker-compose-gpu.yml down"
echo
echo "5. To run the host Python scripts (mainv3.py, orpheus_ttsv3.py):"
echo "   - Open a NEW terminal window/tab in the BASE directory (where this installer script and the Python scripts are located)."
echo "   - Activate the host virtual environment (located inside the installation directory):"
echo "     source \"${INSTALL_DIR_ABS}/host_venv/bin/activate\""
echo "   - Run the desired script (e.g.):"
echo "     ${PYTHON_CMD} mainv3.py --topic \"Your Topic Here\" --keywords \"keyword1,keyword2\""
echo "     # or"
echo "     ${PYTHON_CMD} orpheus_ttsv3.py --script podcast_script_final.txt --dev"
echo "   - Deactivate the environment when finished:"
echo "     deactivate"
echo
echo "--- Important Notes ---"
if [[ "$USE_GPU" == "y" ]]; then
    echo "* Ensure Docker is configured correctly with the NVIDIA Container Toolkit for GPU access."
    echo "* The 'docker-compose-gpu.yml' file is configured for GPU usage."
else
    echo "* No NVIDIA GPU detected. The 'docker-compose-gpu.yml' might still attempt to use GPU resources."
    echo "  You might need to use or create a CPU-specific compose file (e.g., 'docker-compose-cpu.yml') if GPU is unavailable."
fi
echo "* All components (FastAPI app, llama.cpp server, model) are managed by Docker Compose."
echo