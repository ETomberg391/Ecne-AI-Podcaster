#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e
# Treat unset variables as an error when substituting.
set -u
# Pipelines return the exit status of the last command to exit non-zero.
set -o pipefail

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Store the original directory where the script is being run from
ORIGINAL_DIR=$(pwd)

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

# --- TTS Provider Selection ---
TTS_PROVIDER=""

select_tts_provider() {
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║         Ecne AI Podcaster - TTS Provider Selection           ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
    echo "Choose your TTS (Text-to-Speech) provider:"
    echo ""
    echo "  [1] Qwen3 TTS (RECOMMENDED)"
    echo "      • Native Python service (no Docker required)"
    echo "      • High-quality voice synthesis"
    echo "      • Voice cloning capabilities"
    echo "      • 9 preset speakers"
    echo ""
    echo "  [2] Orpheus TTS (Legacy)"
    echo "      • Docker-based setup required"
    echo "      • NVIDIA GPU with Container Toolkit required"
    echo "      • More complex installation"
    echo ""
    
    while true; do
        read -p "Enter your choice [1-2]: " choice
        case $choice in
            1)
                TTS_PROVIDER="qwen3"
                print_info "Selected: Qwen3 TTS"
                break
                ;;
            2)
                TTS_PROVIDER="orpheus"
                print_info "Selected: Orpheus TTS"
                break
                ;;
            *)
                echo "Invalid choice. Please enter 1 or 2."
                ;;
        esac
    done
    echo ""
}

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

# Updated check_command to attempt installation of missing prerequisites
check_command() {
    local cmd="$1"
    local install_suggestion="${2:-}" # Use default empty string if $2 is unset
    local pkg_name="${3:-$cmd}" # Package name might differ from command name, default to cmd name
    local pkg_manager="${4:-}" # Pass detected package manager
    local install_cmd="${5:-}" # Pass install command base

    if ! command -v "$cmd" &> /dev/null; then
        print_warning "Command '$cmd' not found."

        # Only offer to install if we have a package manager and install command
        if [ -n "$pkg_manager" ] && [ -n "$install_cmd" ]; then
            read -p "Do you want to attempt to install '$pkg_name' using $pkg_manager? [Y/n]: " install_prereq
            install_prereq=$(echo "$install_prereq" | tr '[:upper:]' '[:lower:]')

            if [[ "$install_prereq" != "n" ]]; then
                print_info "Attempting to install '$pkg_name'..."
                set +e # Temporarily disable exit on error for the install command
                sudo $install_cmd "$pkg_name"
                local install_exit_code=$?
                set -e # Re-enable exit on error

                if [ $install_exit_code -ne 0 ]; then
                    print_error "Failed to install '$pkg_name' using $pkg_manager (Exit Code: $install_exit_code)."
                    if [ -n "$install_suggestion" ]; then
                         print_error "$install_suggestion"
                    else
                         print_error "Please install it manually."
                    fi
                    exit 1 # Exit if installation failed
                else
                    print_info "'$pkg_name' installed successfully."
                    # Verify command is now available
                    if ! command -v "$cmd" &> /dev/null; then
                         print_error "Installation of '$pkg_name' seemed successful, but command '$cmd' is still not found. Please check your PATH or the installation."
                         exit 1
                    fi
                    # Command is now available, continue script execution
                    return 0
                fi
            else
                # User chose not to install
                local error_msg="Command '$cmd' is required to continue."
                 if [ -n "$install_suggestion" ]; then
                    error_msg="$error_msg $install_suggestion"
                else
                    error_msg="$error_msg Please install it first."
                fi
                print_error "$error_msg"
                exit 1
            fi
        else
            # No package manager detected, just show error and suggestion
            local error_msg="Command '$cmd' not found."
            if [ -n "$install_suggestion" ]; then
                error_msg="$error_msg $install_suggestion"
            else
                error_msg="$error_msg Please install it first."
            fi
            print_error "$error_msg"
            exit 1
        fi
    fi
     # Command exists, return success
     return 0
}


# --- Main Script ---

echo "---------------------------------------------"
echo " Ecne AI Podcaster - Universal TTS Setup     "
echo "---------------------------------------------"

# Select TTS Provider first
select_tts_provider

# If Qwen3 selected, run the simplified installer and exit
if [ "$TTS_PROVIDER" = "qwen3" ]; then
    print_info "Starting Qwen3 TTS setup..."
    
    # Source the Qwen3 installer functions
    if [ -f "$SCRIPT_DIR/Installer_Qwen3_Linux.sh" ]; then
        # Export functions so they're available
        source "$SCRIPT_DIR/Installer_Qwen3_Linux.sh"
        # Run the main function from the Qwen3 installer
        main
        exit 0
    else
        print_error "Installer_Qwen3_Linux.sh not found. Please ensure all installer files are present."
        exit 1
    fi
fi

# Continue with Orpheus setup (legacy path)
print_info "Starting Orpheus TTS setup..."
echo "---------------------------------------------"
echo " Orpheus TTS GGUF Setup Script (V5 - Simplified Build) "
echo "---------------------------------------------"

# --- OS Detection and Package Manager Setup ---
print_info "Detecting operating system and package manager..."

# Initialize variables
OS_TYPE=""
OS_ID=""
PKG_MANAGER=""
INSTALL_CMD=""
UPDATE_CMD=""
CHROME_INSTALLED_VIA_PKG_MANAGER="false" # Flag to track if we used package manager

# Debug information
print_info "OSTYPE: ${OSTYPE:-unknown}"
print_info "uname -s: $(uname -s 2>/dev/null || echo unknown)"

# Check if we're in WSL and set flags accordingly
if grep -q Microsoft /proc/version 2>/dev/null; then
    print_info "Windows Subsystem for Linux (WSL) detected."
    OS_TYPE="linux" # Treat WSL as Linux for package management
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS_ID=$ID
    fi
fi

# Check for Windows (Combined and more robust detection)
# Covers Git Bash, Cygwin, MSYS, and native Windows environments
if [[ "$OSTYPE" == "msys" ]] || \
   [[ "$OSTYPE" == "cygwin" ]] || \
   [[ -n "${SYSTEMROOT:-}" ]] || \
   [[ -d "/c/Windows" ]] || \
   [[ -d "/c/WINDOWS" ]] || \
   [[ -n "$(command -v wmic 2>/dev/null)" ]] || \
   [[ "$(uname -s 2>/dev/null)" =~ ^MINGW|^MSYS ]] || \
   [[ -n "${MINGW_PREFIX:-}" ]] || \
   [[ -n "${MSYSTEM:-}" ]] || \
   [[ -d "/mingw64" ]]; then
    print_info "Windows environment detected (via OSTYPE/env vars/paths)"
    OS_TYPE="windows"
    # Detect Windows version using PowerShell (handle potential errors)
    WIN_VER=$(powershell.exe -NoProfile -Command "[System.Environment]::OSVersion.Version.Major" 2>/dev/null || echo "unknown")
    if [ "$WIN_VER" -eq "10" ] 2>/dev/null; then # Use numeric comparison, suppress errors
        OS_ID="windows10"
        print_info "Detected Windows 10"
    elif [ "$WIN_VER" -eq "11" ] 2>/dev/null; then # Use numeric comparison, suppress errors
        OS_ID="windows11"
        print_info "Detected Windows 11"
    else
        OS_ID="windows"
        print_info "Detected Windows (version unknown or PowerShell failed)"
    fi

    # Check for package managers (Winget/Choco) - INSTALL_CMD will be set if found
    if command -v winget &> /dev/null; then
        PKG_MANAGER="winget"
        INSTALL_CMD="winget install -e --accept-source-agreements --accept-package-agreements"
        print_info "Found winget package manager"
    elif command -v choco &> /dev/null; then
        PKG_MANAGER="choco"
        INSTALL_CMD="choco install -y"
        print_info "Found Chocolatey package manager"
    else
        print_warning "No supported package manager found on Windows (winget or chocolatey). Some prerequisites might need manual installation."
        # Let script continue, but check_command won't offer installs
    fi
# Check for Linux (only if not already identified as Windows or WSL Linux)
elif [ "$OS_TYPE" != "linux" ] && [ -f /etc/os-release ]; then
    OS_TYPE="linux"
    . /etc/os-release
    OS_ID=$ID
    print_info "Detected Linux OS ID: $OS_ID"

    case "$OS_ID" in
        ubuntu|debian|linuxmint|pop|elementary|zorin)
            PKG_MANAGER="apt"
            UPDATE_CMD="sudo apt update"
            INSTALL_CMD="sudo apt install -y"
            ;;
        arch|manjaro|endeavouros|garuda)
            PKG_MANAGER="pacman"
            UPDATE_CMD="sudo pacman -Sy"
            INSTALL_CMD="sudo pacman -S --noconfirm"
            ;;
        fedora|centos|rhel|rocky|almalinux)
            if command -v dnf &> /dev/null; then
                PKG_MANAGER="dnf"
                UPDATE_CMD="sudo dnf check-update"
                INSTALL_CMD="sudo dnf install -y"
            elif command -v yum &> /dev/null; then
                PKG_MANAGER="yum"
                UPDATE_CMD="sudo yum check-update"
                INSTALL_CMD="sudo yum install -y"
            fi
            ;;
        opensuse*|sles)
             PKG_MANAGER="zypper"
             UPDATE_CMD="sudo zypper refresh"
             INSTALL_CMD="sudo zypper install -y"
             ;;
        *)
            if [ -n "${ID_LIKE:-}" ]; then
                print_info "Trying fallback detection based on ID_LIKE='$ID_LIKE'..."
                case "$ID_LIKE" in
                    *debian*) PKG_MANAGER="apt"; UPDATE_CMD="sudo apt update"; INSTALL_CMD="sudo apt install -y";;
                    *arch*) PKG_MANAGER="pacman"; UPDATE_CMD="sudo pacman -Sy"; INSTALL_CMD="sudo pacman -S --noconfirm";;
                    *fedora*)
                        if command -v dnf &> /dev/null; then PKG_MANAGER="dnf"; UPDATE_CMD="sudo dnf check-update"; INSTALL_CMD="sudo dnf install -y";
                        elif command -v yum &> /dev/null; then PKG_MANAGER="yum"; UPDATE_CMD="sudo yum check-update"; INSTALL_CMD="sudo yum install -y"; fi;;
                    *suse*) PKG_MANAGER="zypper"; UPDATE_CMD="sudo zypper refresh"; INSTALL_CMD="sudo zypper install -y";;
                    *) print_warning "Unsupported ID_LIKE ($ID_LIKE) for automatic prerequisite installation."; PKG_MANAGER="";;
                    esac
            else
                 print_warning "Unsupported Linux distribution ($OS_ID) for automatic prerequisite installation."
                 PKG_MANAGER=""
            fi
            ;;
    esac
# Fallback using lsb_release if /etc/os-release wasn't found/parsed
elif [ "$OS_TYPE" != "linux" ] && command -v lsb_release &> /dev/null; then
    OS_TYPE="linux" # Assume Linux if lsb_release exists and we haven't ID'd OS yet
    OS_ID=$(lsb_release -is | tr '[:upper:]' '[:lower:]')
    print_warning "Using fallback OS detection (lsb_release). May be less accurate."
    # Add cases for lsb_release output if needed, similar to above, to set PKG_MANAGER/INSTALL_CMD
    case "$OS_ID" in
        ubuntu|debian) PKG_MANAGER="apt"; UPDATE_CMD="sudo apt update"; INSTALL_CMD="sudo apt install -y";;
        # Add other distros recognized by lsb_release if necessary
        *) print_warning "Unsupported distribution ($OS_ID from lsb_release) for automatic prerequisite installation."; PKG_MANAGER="";;
    esac
else
    # If OS_TYPE is still empty, we couldn't determine the OS/Package Manager
     if [ -z "$OS_TYPE" ]; then
        print_warning "Could not determine operating system or package manager."
        print_warning "Automatic installation of prerequisites will be skipped. Please install manually if needed."
        OS_TYPE="unknown" # Mark as unknown
     fi
fi

if [ -n "$PKG_MANAGER" ]; then
    print_info "Detected Package Manager: $PKG_MANAGER"
fi
echo
# --- End OS Detection ---


print_info "Checking prerequisites..."
# Pass package manager info to check_command
check_command "git" "Please install git (e.g., sudo apt install git)" "git" "$PKG_MANAGER" "$INSTALL_CMD"

print_info "Core prerequisites met."

# --- Host Python Script Prerequisites ---
print_info "Checking prerequisites for host Python scripts (script_builder.py, orpheus_tts.py)..."
check_command "${PYTHON_CMD}" "Please install Python 3 (e.g., sudo apt install python3)" "python3" "$PKG_MANAGER" "$INSTALL_CMD"
check_command "${PIP_CMD}" "Please install pip for Python 3 (e.g., sudo apt install python3-pip)" "python3-pip" "$PKG_MANAGER" "$INSTALL_CMD" # Package name often differs
check_command "ffmpeg" "Please install ffmpeg (e.g., sudo apt install ffmpeg)" "ffmpeg" "$PKG_MANAGER" "$INSTALL_CMD"

# Removed the old warning block about manual installation


# New Docker Installation Block
print_info "Checking for Docker..."
if ! command -v docker &> /dev/null; then
    print_warning "Command 'docker' not found."
    if [ -n "$PKG_MANAGER" ] && [ -n "$INSTALL_CMD" ]; then
        echo
        read -p "Docker is required to run the Orpheus TTS service. Do you want to install Docker using '$PKG_MANAGER'? (Requires sudo) [y/N]: " INSTALL_DOCKER
        INSTALL_DOCKER=$(echo "$INSTALL_DOCKER" | tr '[:upper:]' '[:lower:]')

        if [[ "$INSTALL_DOCKER" == "y" ]]; then
            print_info "Attempting to install Docker using $PKG_MANAGER..."
            # Add specific Docker installation steps for each package manager
            case "$PKG_MANAGER" in
                apt)
                    # Add Docker's official apt repo
                    print_info "Adding Docker's official APT repository..."
                    sudo apt-get update
                    sudo apt-get install -y ca-certificates curl gnupg
                    sudo install -m 0755 -d /etc/apt/keyrings
                    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
                    sudo chmod a+r /etc/apt/keyrings/docker.gpg
                    echo \
                      "deb [arch=\"$(dpkg --print-architecture)\" signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
                      \"$(. /etc/os-release && echo \"\$VERSION_CODENAME\")\" stable" | \
                      sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
                    sudo apt-get update
                    print_info "Installing Docker packages..."
                    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
                    ;;
                pacman)
                    print_info "Installing Docker packages using pacman..."
                    sudo pacman -S --noconfirm --needed docker docker-compose
                    ;;
                dnf|yum)
                    print_info "Installing Docker packages using ${PKG_MANAGER}..."
                    sudo $PKG_MANAGER config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo # For Fedora/CentOS/RHEL
                    sudo $PKG_MANAGER install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
                    ;;
                zypper)
                     print_info "Installing Docker packages using zypper..."
                     sudo zypper addrepo https://download.docker.com/linux/opensuse/docker-ce.repo
                     sudo zypper refresh
                     sudo zypper install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
                     ;;
                *)
                    print_error "Unsupported package manager '$PKG_MANAGER' for automatic Docker installation. Please install Docker manually."
                    ;;
            esac

            INSTALL_EXIT_CODE=$?
            if [ $INSTALL_EXIT_CODE -eq 0 ]; then
                print_info "Docker installation attempt finished successfully."
                print_info "Consider adding your user to the 'docker' group to run Docker without sudo:"
                print_info "  sudo usermod -aG docker \$USER"
                print_info "You may need to log out and log back in for the group change to take effect."
            else
                print_error "Docker installation attempt failed (Exit Code: $INSTALL_EXIT_CODE). Please install Docker manually: https://docs.docker.com/engine/install/"
            fi
        else
            print_error "Docker is required and was not installed automatically. Please install Docker manually to continue: https://docs.docker.com/engine/install/"
        fi
    else
        print_error "Docker is required but could not be found, and your Linux distribution could not be automatically detected for installation. Please install Docker manually: https://docs.docker.com/engine/install/"
    fi
else
    print_info "Docker found."
fi

# Check if user is in the docker group
print_info "Checking if the current user is in the 'docker' group..."
if id -nG "$USER" | grep -qw "docker"; then
    print_info "User '$USER' is already in the 'docker' group."
else
    print_warning "User '$USER' is NOT in the 'docker' group."
    echo
    read -p "Adding your user to the 'docker' group is required to run Docker commands without sudo. Do you want to add '$USER' to the 'docker' group? (Requires sudo and logging out/in) [y/N]: " ADD_TO_DOCKER_GROUP
    ADD_TO_DOCKER_GROUP=$(echo "$ADD_TO_DOCKER_GROUP" | tr '[:upper:]' '[:lower:]')

    if [[ "$ADD_TO_DOCKER_GROUP" == "y" ]]; then
        print_info "Attempting to add user '$USER' to the 'docker' group..."
        set +e # Temporarily disable exit on error
        sudo usermod -aG docker "$USER"
        usermod_exit_code=$?
        set -e # Re-enable exit on error

        if [ $usermod_exit_code -eq 0 ]; then
            print_info "Successfully added user '$USER' to the 'docker' group."
            print_info "IMPORTANT: You must log out and log back in for the group changes to take effect."
        else
            print_error "Failed to add user '$USER' to the 'docker' group (Exit Code: $usermod_exit_code)."
            print_error "Please add your user to the 'docker' group manually and log out/in."
            exit 1 # Exit if adding user failed
        fi
    else
        print_error "User '$USER' is not in the 'docker' group, which is required to run Docker commands without sudo. Aborting."
        exit 1 # Exit if user declined
    fi
fi


# Now check for docker compose syntax after Docker is confirmed installed
print_info "Checking for Docker Compose..."
if command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker-compose"
    print_info "Found 'docker-compose' (V1 syntax)."
elif docker compose version &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker compose"
    print_info "Found 'docker compose' (V2 syntax)."
else
    # This case should ideally not be hit if docker-compose-plugin was installed with Docker,
    # but keep as a fallback.
    print_error "Docker Compose not found. Please install Docker Compose (V1 or V2). See: https://docs.docker.com/compose/install/"
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
          if [ -n "$PKG_MANAGER" ] && [ -n "$INSTALL_CMD" ]; then
              echo
              read -p "The NVIDIA Container Toolkit is required for Docker to access the GPU. Do you want to install it using '$PKG_MANAGER'? (Requires sudo) [y/N]: " INSTALL_NVIDIA_TOOLKIT
              INSTALL_NVIDIA_TOOLKIT=$(echo "$INSTALL_NVIDIA_TOOLKIT" | tr '[:upper:]' '[:lower:]')

              if [[ "$INSTALL_NVIDIA_TOOLKIT" == "y" ]]; then
                  print_info "Attempting to install NVIDIA Container Toolkit using $PKG_MANAGER..."
                  # Add specific installation steps based on Docker's guide
                  case "$PKG_MANAGER" in
                      apt)
                          # Add NVIDIA Container Toolkit's official apt repo
                          print_info "Adding NVIDIA Container Toolkit's official APT repository..."
                          curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
                          curl -s -L https://nvidia.github.io/libnvidia-container/ubuntu/nvidia-container-toolkit.list | \
                              sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
                              sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
                          sudo apt-get update
                          print_info "Installing NVIDIA Container Toolkit..."
                          sudo apt-get install -y nvidia-container-toolkit
                          sudo nvidia-ctk runtime configure --runtime=docker
                          sudo systemctl restart docker
                          ;;
                      pacman)
                          print_info "Installing NVIDIA Container Toolkit using pacman..."
                          sudo pacman -S --noconfirm --needed nvidia-container-toolkit
                          ;;
                      dnf|yum)
                          print_info "Installing NVIDIA Container Toolkit using ${PKG_MANAGER}..."
                          sudo $PKG_MANAGER install -y nvidia-container-toolkit
                          ;;
                      zypper)
                               print_info "Installing NVIDIA Container Toolkit using zypper..."
                               sudo zypper install -y nvidia-container-toolkit
                               ;;
                          *)
                              print_error "Unsupported package manager '$PKG_MANAGER' for automatic NVIDIA Container Toolkit installation. Please install it manually."
                              ;;
                      esac

                      INSTALL_EXIT_CODE=$?
                      if [ $INSTALL_EXIT_CODE -eq 0 ]; then
                          print_info "NVIDIA Container Toolkit installation attempt finished successfully."
                      else
                          print_error "NVIDIA Container Toolkit installation attempt failed (Exit Code: $INSTALL_EXIT_CODE). Please install it manually: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html"
                      fi
                  else
                      print_error "NVIDIA Container Toolkit is required for GPU access and was not installed automatically. Please install it manually to continue: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html"
                  fi
              else
                  print_error "NVIDIA Container Toolkit is required for GPU access but could not be found, and your Linux distribution could not be automatically detected for installation. Please install it manually: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html"
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
    elif [ -z "$(ls -A .)" ]; then
        # Directory is empty, safe to clone
        print_info "Cloning Orpheus-FastAPI repository..."
        git clone https://github.com/Lex-au/Orpheus-FastAPI.git .
    else
        # Directory is not empty and not a git repo, assume files are present
        print_warning "Directory '.' exists and is not empty, but not a git repository. Skipping clone and assuming files are present."
        print_warning "The docker compose command will use the existing files in this directory."
    fi
    print_info "Orpheus-FastAPI source code is ready."
    # Check if .env exists in the cloned directory
    if [ ! -f ".env" ]; then
        print_info "Copying .env.example to .env in Orpheus-FastAPI directory..."
        if [ -f ".env.example" ]; then
            cp ".env.example" ".env"
            print_info ".env created from .env.example in Orpheus-FastAPI directory."
        else
            print_warning ".env.example not found in Orpheus-FastAPI directory. Cannot create .env."
        fi
    else
        print_warning ".env already exists in Orpheus-FastAPI directory. Skipping copy."
    fi

    cd "$ORIGINAL_DIR" # Go back to the directory where the script was run from

    # --- .env Configuration (Root Directory) ---
    # Corrected path for .env file
    ROOT_ENV_PATH="$SCRIPT_DIR/.env"
    EXAMPLE_ENV_PATH="$SCRIPT_DIR/settings/env.example"
 
    if [ ! -f "$ROOT_ENV_PATH" ]; then
        print_info "Copying $EXAMPLE_ENV_PATH to $ROOT_ENV_PATH..."
        cp "$EXAMPLE_ENV_PATH" "$ROOT_ENV_PATH"
    else
        print_warning "$ROOT_ENV_PATH already exists in root directory. Skipping copy from $EXAMPLE_ENV_PATH."
    fi
 
 
    # Determine expected activation script path first
    VENV_ACTIVATE=""
    if [ "$OS_TYPE" = "windows" ]; then
        VENV_ACTIVATE="./host_venv/Scripts/activate"
    else
        VENV_ACTIVATE="./host_venv/bin/activate"
    fi
 
    # --- Setup Host Python Environment (for script_builder.py, orpheus_tts.py) ---
    print_info "Setting up Python virtual environment for host scripts (script_builder.py, orpheus_tts.py)..."
 
    if [ ! -d "host_venv" ]; then
        print_info "Creating Python virtual environment 'host_venv' for host scripts..."
        $PYTHON_CMD -m venv "host_venv"
    else
        print_warning "Host virtual environment 'host_venv' already exists. Skipping creation."
        print_warning "If you encounter issues, remove the 'host_venv' directory and re-run the script."
    fi
 
    print_info "Activating host virtual environment and installing dependencies from requirements_host.txt..."
    # Use subshell to activate, install, and deactivate without affecting parent script's environment
    (
        if [ ! -f "$VENV_ACTIVATE" ]; then
            print_error "Virtual environment activation script not found at: $VENV_ACTIVATE"
        fi
 
        source "$VENV_ACTIVATE"
        print_info "Upgrading pip in host venv..."
        $PIP_CMD install --upgrade pip
 
        # Corrected path for requirements_host.txt
        if [ -f "$SCRIPT_DIR/requirements_host.txt" ]; then
            print_info "Installing host dependencies from $SCRIPT_DIR/requirements_host.txt..."
            $PIP_CMD install -r "$SCRIPT_DIR/requirements_host.txt"
            
            # Check Python version and install audioop-lts if Python 3.13+
            python_major=$($PYTHON_CMD -c "import sys; print(sys.version_info.major)" 2>/dev/null)
            python_minor=$($PYTHON_CMD -c "import sys; print(sys.version_info.minor)" 2>/dev/null)
            
            if [ $? -eq 0 ] && [ -n "$python_major" ] && [ -n "$python_minor" ]; then
                # Convert to numeric comparison
                if [ "$python_major" -gt 3 ] || ([ "$python_major" -eq 3 ] && [ "$python_minor" -ge 13 ]); then
                    print_info "Python $python_major.$python_minor detected. Installing audioop-lts for Python 3.13+ compatibility..."
                    $PIP_CMD install audioop-lts
                else
                    print_info "Python $python_major.$python_minor detected. Using built-in audioop module (audioop-lts not needed)."
                fi
            else
                print_warning "Could not determine Python version. Skipping audioop-lts installation."
            fi
            
            # Download NLTK data (punkt) after installation
            print_info "Downloading NLTK 'punkt' tokenizer data (required for sentence splitting)..."
            $PYTHON_CMD -m nltk.downloader punkt
            print_info "Downloading NLTK 'punkt_tab' tokenizer data (required for some scraping/processing)..."
            $PYTHON_CMD -m nltk.downloader punkt_tab
        else
            # Deactivate before erroring
            deactivate
            print_error "Could not find $SCRIPT_DIR/requirements_host.txt. Cannot install host dependencies."
        fi
        print_info "Deactivating venv..."
        deactivate
    )
    print_info "Host Python environment setup complete."
    echo
 
    # --- Optional System Dependency Installation ---
    # (Tkinter, libsndfile, PortAudio)
    if [ -n "$PKG_MANAGER" ] && [ -n "$INSTALL_CMD" ]; then
        echo
        # Define dependencies based on detected OS/package manager
        DEPS_TO_INSTALL=""
        case "$PKG_MANAGER" in
            apt)
                # python3-dev is needed for building C extensions like audioop during venv creation/package installation
                # python3-tk is for Tkinter GUI
                # libsndfile1 is for soundfile library
                # portaudio19-dev is for pyaudio (if used, though soundfile is preferred)
                DEPS_TO_INSTALL="python3-dev python3-tk libsndfile1 portaudio19-dev"
                ;;
            pacman)
                # python includes development headers on Arch
                # tk is for Tkinter GUI
                # libsndfile is for soundfile library
                # portaudio is for pyaudio
                # Added dependencies for audioop/pydub compilation
                DEPS_TO_INSTALL="python tk libsndfile portaudio libffi zlib openssl"
                ;;
            dnf|yum)
                # python3-devel is needed for building C extensions
                # python3-tkinter is for Tkinter GUI
                # libsndfile is for soundfile library
                # portaudio-devel is for pyaudio
                DEPS_TO_INSTALL="python3-devel python3-tkinter libsndfile portaudio-devel"
                ;;
            zypper)
                # python3-devel is needed for building C extensions
                # python3-tk is for Tkinter GUI
                # libsndfile1 is for soundfile library
                # portaudio-devel is for pyaudio
                DEPS_TO_INSTALL="python3-devel python3-tk libsndfile1 portaudio-devel"
                ;;
            *)
                print_warning "Unsupported package manager '$PKG_MANAGER' for automatic system dependency installation."
                DEPS_TO_INSTALL="" # Clear deps if unsupported
                ;;
        esac

        if [ -n "$DEPS_TO_INSTALL" ]; then
            print_warning "The following system packages are recommended or required for host scripts (e.g., building Python modules like audioop, GUI, audio processing):"
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

                if [ $INSTALL_EXIT_CODE == 0 ]; then
                    print_info "System dependency installation attempt finished successfully."
                else
                    print_error "System dependency installation attempt failed (Exit Code: $INSTALL_EXIT_CODE). Please install them manually: $DEPS_TO_INSTALL"
                fi
            else
                print_info "Skipping automatic system dependency installation. Please ensure they are installed manually if needed."
            fi
        fi
    else
        print_warning "Could not detect package manager. Skipping automatic system dependency installation."
    fi
    echo


    # --- Optional Chrome/ChromeDriver Installation (for host_venv) ---
    # Define path relative to script location (assuming script is run from repo root)
    CHROMEDRIVER_DIR="./host_venv/bin"
    CHROMEDRIVER_PATH="${CHROMEDRIVER_DIR}/chromedriver"
 
    # --- ChromeDriver Setup Functions ---
 
    # Function to find installed Chrome/Chromium version
    get_chrome_version() {
        local chrome_version=""
        # Try common commands
        if command -v google-chrome-stable &> /dev/null; then
            chrome_version=$(google-chrome-stable --version 2>/dev/null)
        elif command -v google-chrome &> /dev/null; then
            chrome_version=$(google-chrome --version 2>/dev/null)
        elif command -v chromium-browser &> /dev/null; then
            chrome_version=$(chromium-browser --version 2>/dev/null)
        elif command -v chromium &> /dev/null; then
            chrome_version=$(chromium --version 2>/dev/null)
        fi
 
        # Extract version number (e.g., "Google Chrome 114.0.5735.198" -> "114.0.5735.198")
        # Handles variations like "Chromium 114..."
        chrome_version=$(echo "$chrome_version" | grep -oP '(\d+\.\d+\.\d+\.\d+)' | head -n 1)
 
        if [ -n "$chrome_version" ]; then
            echo "$chrome_version"
        else
            return 1 # Indicate not found
        fi
    }
 
    # Function to check local ChromeDriver version
    get_local_chromedriver_version() {
        if [ -f "$CHROMEDRIVER_PATH" ] && [ -x "$CHROMEDRIVER_PATH" ]; then
            local driver_version_output=$("$CHROMEDRIVER_PATH" --version 2>/dev/null)
            # Extract version (e.g., "ChromeDriver 114.0.5735.90 ..." -> "114.0.5735.90")
            local driver_version=$(echo "$driver_version_output" | grep -oP 'ChromeDriver\s+(\d+\.\d+\.\d+\.\d+)' | sed -n 's/ChromeDriver //p')
            if [ -n "$driver_version" ]; then
                echo "$driver_version"
            else
                 # Handle cases where version format might differ or command fails silently
                 print_warning "Could not parse version from existing ChromeDriver at $CHROMEDRIVER_PATH"
                 echo "" # Return empty if parsing fails
            fi
        else
            echo "" # Return empty if not found or not executable
        fi
    }
 
    # Function to download and install ChromeDriver matching a major Chrome version
    install_local_chromedriver() {
        local required_major_version="$1"
        # Use the more targeted endpoint first
        local latest_patch_url="https://googlechromelabs.github.io/chrome-for-testing/latest-patch-versions-per-build-with-downloads.json"
        # Fallback endpoint if the exact build isn't in the latest-patch endpoint
        local milestone_url="https://googlechromelabs.github.io/chrome-for-testing/latest-versions-per-milestone-with-downloads.json"
 
        local temp_zip="/tmp/chromedriver_linux64.zip"
        local temp_extract_dir="/tmp/chromedriver_extract"
        local download_url=""
        local chrome_full_version=$(get_chrome_version) # Get the full installed version
        local chrome_build_version=$(echo "$chrome_full_version" | cut -d. -f1-3) # Extract major.minor.build
 
        print_info "Installed Chrome version: $chrome_full_version (Major.Minor.Build: $chrome_build_version)"
        print_info "Attempting to find exact ChromeDriver match using latest-patch endpoint..."
 
        # Attempt 1: Find the exact build version in the latest-patch endpoint
        download_url=$(curl -s "$latest_patch_url" | jq -r --arg build "$chrome_build_version" '
            .builds[$build].downloads.chromedriver[]? |
            select(.platform == "linux64") |
            .url // empty
        ' 2>/dev/null)
 
        # Attempt 2: If exact build not found, fall back to the latest milestone endpoint
        if [ -z "$download_url" ]; then
            print_warning "Exact match for build $chrome_build_version not found in latest-patch data."
            print_info "Attempting to find latest ChromeDriver for major version $required_major_version using milestone endpoint..."
            download_url=$(curl -s "$milestone_url" | jq -r --arg milestone "$required_major_version" '
                .milestones[$milestone].downloads.chromedriver[]? |
                select(.platform == "linux64") |
                .url // empty
            ' 2>/dev/null)
 
            if [ -z "$download_url" ]; then
                 print_error "Could not find a suitable linux64 ChromeDriver download URL for Chrome major version $required_major_version using milestone endpoint either."
                 print_warning "Please install ChromeDriver manually from https://googlechromelabs.github.io/chrome-for-testing/"
                 return 1
             else
                  print_info "Found latest ChromeDriver URL for major version $required_major_version via milestone endpoint."
             fi
         else
             print_info "Found exact ChromeDriver URL for build $chrome_build_version via latest-patch endpoint."
         fi
 
         # Proceed with download using the found URL
         print_info "Downloading ChromeDriver from: $download_url"
         if ! curl -L -o "$temp_zip" "$download_url"; then
             print_error "Failed to download ChromeDriver from $download_url"
             rm -f "$temp_zip"
             return 1
         fi
 
         print_info "Extracting ChromeDriver..."
         rm -rf "$temp_extract_dir" # Clean up previous attempt if any
         mkdir -p "$temp_extract_dir"
         # Extract directly into the target directory structure if possible, handling potential nested folders
         # The zip file from google contains a top-level directory like chromedriver-linux64/
         if ! unzip -q "$temp_zip" -d "$temp_extract_dir"; then
             print_error "Failed to unzip $temp_zip"
             rm -f "$temp_zip"
             rm -rf "$temp_extract_dir"
             return 1
         fi
 
         # Find the chromedriver executable (it's often in a nested folder like chromedriver-linux64/chromedriver)
         local extracted_driver_path=$(find "$temp_extract_dir" -name chromedriver -type f -executable | head -n 1)
 
 
         if [ -z "$extracted_driver_path" ]; then
             print_error "Could not find 'chromedriver' executable in the extracted archive."
             rm -f "$temp_zip"
             rm -rf "$temp_extract_dir"
             return 1
         fi
 
         print_info "Installing ChromeDriver to $CHROMEDRIVER_PATH..."
         # Ensure the target directory exists (should be created by venv setup)
         mkdir -p "$CHROMEDRIVER_DIR"
         # Move the found executable directly, overwriting if necessary
         if ! mv "$extracted_driver_path" "$CHROMEDRIVER_PATH"; then
              print_error "Failed to move ChromeDriver to $CHROMEDRIVER_PATH"
              # Don't remove the zip/extract dir yet, user might want to inspect
              return 1
         fi
 
         # Ensure it's executable after moving (mv should preserve permissions, but double-check)
         if ! chmod +x "$CHROMEDRIVER_PATH"; then
             print_error "Failed to ensure ChromeDriver is executable at $CHROMEDRIVER_PATH"
             # Attempt to remove the potentially corrupted file
             rm -f "$CHROMEDRIVER_PATH"
             # Don't remove the zip/extract dir yet
             return 1
         fi
 
         # Clean up
         rm -f "$temp_zip"
         rm -rf "$temp_extract_dir"
 
         local installed_version=$(get_local_chromedriver_version)
         if [ -n "$installed_version" ]; then
              print_info "ChromeDriver installation successful. Version: $installed_version"
              return 0
         else
              print_error "ChromeDriver installed, but failed to verify version."
              return 1
         fi
     }
 
     # --- End ChromeDriver Setup Functions ---
 
 
     if [ -n "$PKG_MANAGER" ] && [ -n "$INSTALL_CMD" ]; then
         echo
         read -p "Do you want to attempt to install/update Google Chrome/Chromium using $PKG_MANAGER? (Browser is required for Selenium features) [y/N]: " INSTALL_CHROME
         INSTALL_CHROME=$(echo "$INSTALL_CHROME" | tr '[:upper:]' '[:lower:]')
 
         if [[ "$INSTALL_CHROME" == "y" ]]; then
             GOOGLE_CHROME_INSTALLED_FLAG="false" # Track if google-chrome was installed specifically
             print_info "Attempting to install/update Chrome/Chromium using $PKG_MANAGER..."
             if [ -n "$UPDATE_CMD" ]; then
                 print_info "Running package list update ($UPDATE_CMD)..."
                 set +e
                 $UPDATE_CMD
                 if [ $? -ne 0 ]; then print_warning "Package list update failed. Installation might use outdated lists or fail."; fi
                 set -e
             fi
 
             print_info "Running installation..."
             set +e # Don't exit immediately if install fails
             INSTALL_EXIT_CODE=0
 
             case "$PKG_MANAGER" in
                 winget)
                     # Install Google Chrome using winget
                     print_info "Attempting to install Google Chrome using winget..."
                     $INSTALL_CMD Google.Chrome # Winget package name
                     INSTALL_EXIT_CODE=$?
                     if [ $INSTALL_EXIT_CODE -eq 0 ]; then
                         CHROME_INSTALLED_VIA_PKG_MANAGER="true"
                     fi
                     ;;
                 choco)
                     # Install Google Chrome using chocolatey
                     print_info "Attempting to install Google Chrome using chocolatey..."
                     $INSTALL_CMD googlechrome # Choco package name
                     INSTALL_EXIT_CODE=$?
                     if [ $INSTALL_EXIT_CODE -eq 0 ]; then
                         CHROME_INSTALLED_VIA_PKG_MANAGER="true"
                     fi
                     ;;
                 apt)
                     # Install Google Chrome (adds repo)
                     print_info "Attempting to install Google Chrome Stable via official repository..."
                     wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | sudo apt-key add - > /dev/null 2>&1
                     sudo sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list'
                     $UPDATE_CMD # Update again after adding repo
                     sudo $INSTALL_CMD google-chrome-stable
                     INSTALL_EXIT_CODE=$?
                     GOOGLE_CHROME_INSTALLED_FLAG="true" # Mark that we tried to install google-chrome
                     ;;
                 dnf|yum)
                     # Install Chromium (driver handled by webdriver-manager)
                     print_info "Attempting to install Chromium using $PKG_MANAGER..."
                     sudo $INSTALL_CMD chromium # Package name on dnf/yum
                     INSTALL_EXIT_CODE=$?
                     CHROME_INSTALLED_VIA_PKG_MANAGER="true"
                     ;;
                 pacman)
                     # Use --needed to only install if missing or outdated (driver handled by webdriver-manager)
                     print_info "Attempting to install Chromium using $PKG_MANAGER..."
                     sudo $INSTALL_CMD --needed chromium # Package name on pacman
                     INSTALL_EXIT_CODE=$?
                     CHROME_INSTALLED_VIA_PKG_MANAGER="true"
                     ;;
                 zypper)
                      # Driver handled by webdriver-manager
                     print_info "Attempting to install Chromium using $PKG_MANAGER..."
                     sudo $INSTALL_CMD chromium # Package name on zypper
                     INSTALL_EXIT_CODE=$?
                     CHROME_INSTALLED_VIA_PKG_MANAGER="true"
                     ;;
             esac
             set -e # Re-enable exit on error
 
             if [ $INSTALL_EXIT_CODE -eq 0 ]; then
                 print_info "Package manager installation attempt finished successfully."
             else
                 print_warning "Package manager installation attempt finished with Exit Code: $INSTALL_EXIT_CODE."
                 # Don't error out here, let the chromedriver check proceed
             fi
 
             # --- Check and Install ChromeDriver ---
             print_info "Checking installed Chrome/Chromium version..."
             chrome_full_version=$(get_chrome_version)
 
             if [ -z "$chrome_full_version" ]; then
                  print_warning "Could not detect installed Chrome/Chromium version after installation attempt."
                  print_warning "Skipping ChromeDriver setup. Please ensure a compatible version is installed manually or via report_builder.py."
             else
                 chrome_major_version=$(echo "$chrome_full_version" | cut -d. -f1)
                 print_info "Detected Chrome/Chromium version: $chrome_full_version (Major: $chrome_major_version)"
 
                 print_info "Checking local ChromeDriver version at $CHROMEDRIVER_PATH..."
                 driver_full_version=$(get_local_chromedriver_version)
                 should_install_driver="true"
 
                 if [ -n "$driver_full_version" ]; then
                     driver_major_version=$(echo "$driver_full_version" | cut -d. -f1)
                     print_info "Found local ChromeDriver version: $driver_full_version (Major: $driver_major_version)"
                     if [ "$driver_major_version" = "$chrome_major_version" ]; then
                         print_info "Local ChromeDriver version is compatible."
                         should_install_driver="false"
                     else
                         print_warning "Local ChromeDriver version mismatch. Will attempt to install matching version."
                     fi
                 else
                      print_info "Local ChromeDriver not found or version unknown. Will attempt to install."
                 fi
 
                 if [ "$should_install_driver" = "true" ]; then
                      install_local_chromedriver "$chrome_major_version"
                      # The function install_local_chromedriver prints success/error messages
                 fi
             fi
             # --- End ChromeDriver Check ---
 
         else
             print_info "Skipping automatic Chrome/ChromeDriver installation."
             print_info "Skipping automatic Chrome/Chromium installation by user choice."
             # Still check existing chrome/driver if chrome wasn't installed by script
             print_info "Checking installed Chrome/Chromium version..."
             chrome_full_version=$(get_chrome_version)
             if [ -z "$chrome_full_version" ]; then
                 print_warning "Could not detect installed Chrome/Chromium version."
                 print_warning "Please ensure Chrome/Chromium AND a matching ChromeDriver are installed for Selenium features."
             else
                 chrome_major_version=$(echo "$chrome_full_version" | cut -d. -f1)
                 print_info "Detected Chrome/Chromium version: $chrome_full_version (Major: $chrome_major_version)"
                 print_info "Checking local ChromeDriver version at $CHROMEDRIVER_PATH..."
                 driver_full_version=$(get_local_chromedriver_version)
                  if [ -n "$driver_full_version" ]; then
                     driver_major_version=$(echo "$driver_full_version" | cut -d. -f1)
                     print_info "Found local ChromeDriver version: $driver_full_version (Major: $driver_major_version)"
                     if [ "$driver_major_version" != "$chrome_major_version" ]; then
                          print_warning "Local ChromeDriver version does NOT match Chrome/Chromium version."
                          print_warning "Attempting to install matching ChromeDriver..."
                          install_local_chromedriver "$chrome_major_version"
                     else
                          print_info "Local ChromeDriver version is compatible."
                     fi
                 else
                      print_warning "Local ChromeDriver not found or version unknown."
                      print_warning "Attempting to install matching ChromeDriver..."
                      install_local_chromedriver "$chrome_major_version"
                 fi
             fi
         fi
     else
         print_warning "Could not detect package manager. Skipping automatic Chrome/Chromium installation."
         # Still check existing chrome/driver if package manager wasn't found
         print_info "Checking installed Chrome/Chromium version..."
         chrome_full_version=$(get_chrome_version)
          if [ -z "$chrome_full_version" ]; then
             print_warning "Could not detect installed Chrome/Chromium version."
             print_warning "Please ensure Chrome/Chromium AND a matching ChromeDriver are installed for Selenium features."
         else
             chrome_major_version=$(echo "$chrome_full_version" | cut -d. -f1)
             print_info "Detected Chrome/Chromium version: $chrome_full_version (Major: $chrome_major_version)"
             print_info "Checking local ChromeDriver version at $CHROMEDRIVER_PATH..."
             driver_full_version=$(get_local_chromedriver_version)
              if [ -n "$driver_full_version" ]; then
                 driver_major_version=$(echo "$driver_full_version" | cut -d. -f1)
                 print_info "Found local ChromeDriver version: $driver_full_version (Major: $driver_major_version)"
                 if [ "$driver_major_version" != "$chrome_major_version" ]; then
                      print_warning "Local ChromeDriver version does NOT match Chrome/Chromium version."
                      print_warning "Attempting to install matching ChromeDriver..."
                      install_local_chromedriver "$chrome_major_version"
                 else
                      print_info "Local ChromeDriver version is compatible."
                 fi
             else
                  print_warning "Local ChromeDriver not found or version unknown."
                  print_warning "Attempting to install matching ChromeDriver..."
                  install_local_chromedriver "$chrome_major_version"
             fi
         fi
     fi
     echo
     print_info "Chrome and ChromeDriver installation check complete for host_venv."
 
 
     # --- Google API Configuration ---
     read -p "Do you want to use Google API? The setup is more difficult than setting up Brave API and has a 100/day searching limit (y/N): " USE_GOOGLE_API
     USE_GOOGLE_API=$(echo "$USE_GOOGLE_API" | tr '[:upper:]' '[:lower:]')
     if [[ "$USE_GOOGLE_API" == "y" ]]; then
         echo "Get API Key from Google Cloud Console (Credentials page)"
         read -p "Enter GOOGLE_API_KEY= " GOOGLE_API_KEY
         echo "Get Search Engine ID (cx) from Programmable Search Engine control panel (make sure \"Search entire web\" is ON)"
         read -p "Enter GOOGLE_CSE_ID= " GOOGLE_CSE_ID
 
         # Update .env with Google API keys - Corrected path
         sed -i "s/^GOOGLE_API_KEY=.*/GOOGLE_API_KEY=\"${GOOGLE_API_KEY}\"/" "$SCRIPT_DIR/.env"
         sed -i "s/^GOOGLE_CSE_ID=.*/GOOGLE_CSE_ID=\"${GOOGLE_CSE_ID}\"/" "$SCRIPT_DIR/.env"
     fi
 
     # --- Brave API Configuration ---
     read -p "Do you want to enter the Brave API key? (Y/n): " USE_BRAVE_API
     USE_BRAVE_API=$(echo "$USE_BRAVE_API" | tr '[:upper:]' '[:lower:]')
     if [[ "$USE_BRAVE_API" != "n" ]]; then
         echo "Brave Search API Key (Get from https://api.search.brave.com/)"
         read -p "BRAVE_API_KEY= " BRAVE_API_KEY
 
         # Update .env with Brave API key - Corrected path
         sed -i "s/^BRAVE_API_KEY=.*/BRAVE_API_KEY=\"${BRAVE_API_KEY}\"/" "$SCRIPT_DIR/.env"
     fi
 
     # --- ai_models.yml Configuration ---
     # Corrected paths for ai_models.yml
     AI_MODELS_YML_PATH="$SCRIPT_DIR/settings/llm_settings/ai_models.yml"
     EXAMPLE_AI_MODELS_YML_PATH="$SCRIPT_DIR/settings/llm_settings/example_ai_models.yml"
 
     if [ ! -f "$AI_MODELS_YML_PATH" ]; then
         print_info "Copying $EXAMPLE_AI_MODELS_YML_PATH to $AI_MODELS_YML_PATH..."
         # Ensure the target directory exists before copying
         mkdir -p $(dirname "$AI_MODELS_YML_PATH")
         if [ -f "$EXAMPLE_AI_MODELS_YML_PATH" ]; then
             cp "$EXAMPLE_AI_MODELS_YML_PATH" "$AI_MODELS_YML_PATH"
             print_info "$AI_MODELS_YML_PATH created from example."
         else
             print_error "Example AI models file not found: $EXAMPLE_AI_MODELS_YML_PATH. Cannot proceed."
         fi
     else
         print_warning "$AI_MODELS_YML_PATH already exists. Skipping copy from example."
         print_warning "Please review your existing $AI_MODELS_YML_PATH file manually."
     fi
 
     # --- Gemini API Configuration ---
     read -p "Do you want to use the recommended free Google Gemini 2.0 Flash Exp model with this project? (Y/n): " USE_GEMINI
     USE_GEMINI=$(echo "$USE_GEMINI" | tr '[:upper:]' '[:lower:]')
     if [[ "$USE_GEMINI" != "n" ]]; then
         echo "You can get a GoogleGemini API key from https://ai.google.dev/gemini-api/docs/api-key"
         read -p "Enter api_key: " GEMINI_API_KEY
 
         # Update ai_models.yml with Gemini API key and .env with FAULT_MODEL_CONFIG
         # Corrected sed command and path
         sed -i "s/api_key: \"\"/api_key: \"${GEMINI_API_KEY}\"/g" "$AI_MODELS_YML_PATH"
         # Corrected path for .env
         sed -i "s/^DEFAULT_MODEL_CONFIG=.*/DEFAULT_MODEL_CONFIG=\"gemini_flash\"/" "$SCRIPT_DIR/.env"
     else
         # --- OpenAI API Configuration ---
         echo "Please enter the OpenAI API compatible server settings:"
         read -p "api_endpoint: " OPENAI_API_ENDPOINT
         read -p "api_key: " OPENAI_API_KEY
         read -p "model: (default ChatGPT4o if nothing entered) " OPENAI_MODEL
         OPENAI_MODEL=${OPENAI_MODEL:-"ChatGPT4o"}
         read -p "temperature: (Default 0.7 if nothing entered) " OPENAI_TEMPERATURE
         OPENAI_TEMPERATURE=${OPENAI_TEMPERATURE:-0.7}
 
         # Update ai_models.yml with OpenAI API settings - Corrected path
         sed -i "s#api_endpoint: \"\"#api_endpoint: \"${OPENAI_API_ENDPOINT}\"#g" "$AI_MODELS_YML_PATH"
         sed -i "s#api_key: \"sk1-example\"#api_key: \"${OPENAI_API_KEY}\"#g" "$AI_MODELS_YML_PATH"
         sed -i "s#model: \"QwQ-32B_Example\"#model: \"${OPENAI_MODEL}\"#g" "$AI_MODELS_YML_PATH"
         sed -i "s#temperature: 0.7#temperature: ${OPENAI_TEMPERATURE}#g" "$AI_MODELS_YML_PATH"
 
         # Update .env with FAULT_MODEL_CONFIG to default_model - Corrected path
         sed -i "s/^DEFAULT_MODEL_CONFIG=.*/DEFAULT_MODEL_CONFIG=\"default_model\"/" "$SCRIPT_DIR/.env"
     fi
 
     # --- Final Instructions ---
     echo
     echo "---------------------------------------------"
     echo " Setup Complete! "
     echo "---------------------------------------------"
     echo
     echo "The necessary source code for Orpheus-FastAPI has been cloned/updated into:"
     echo "  $FASTAPI_DIR"
     echo
 
     # Add WSL-specific notes if in WSL environment
     if grep -q Microsoft /proc/version 2>/dev/null; then
         echo
         echo "NOTE: WSL Environment Detected"
         echo "- Chrome/ChromeDriver: Use Windows Chrome installation"
         echo "- Browser automation will use Windows Chrome through WSL integration"
     fi
     echo
 
     echo "Next Steps:"
     echo
 
     echo "1. Start the services using Docker Compose:"
     echo "   cd \"$FASTAPI_DIR\""
     echo "   $DOCKER_COMPOSE_CMD -f docker-compose-gpu.yml up"
     echo "   (Add '-d' to run in detached mode: $DOCKER_COMPOSE_CMD -f docker-compose-gpu.yml up -d)"
     echo
     echo "2. Access the Web UI:"
     echo "   Once the containers are running, access the UI in your browser at:"
     # Use the default port from the compose file, as we didn't ask the user
     # Assuming the compose file maps to port 5005 on the host by default
     echo "   http://127.0.0.1:5005"
     echo
     echo "3. To stop the services:"
     echo "   Press Ctrl+C in the terminal where compose is running, or if detached:"
     echo "   $DOCKER_COMPOSE_CMD -f docker-compose-gpu.yml down"
     echo
     echo "4. To run the host Python scripts (script_builder.py, orpheus_tts.py):"
     echo "   - Open a NEW terminal window/tab in the BASE directory (where this installer script and the Python scripts are located)."
     echo "   - Activate the host virtual environment:"
     echo "     source \"./host_venv/bin/activate\""
     echo "   - Run the desired script (e.g.):"
     echo "     ${PYTHON_CMD} \"$SCRIPT_DIR/script_builder.py\" --topic \"Your Topic Here\" --keywords \"keyword1,keyword2\""
     echo "     # or"
     echo "     ${PYTHON_CMD} \"$SCRIPT_DIR/orpheus_tts.py\" --script podcast_script_final.txt --dev"
     echo
     echo "   - Deactivate the environment when finished: Deactivate"
     echo
     echo "5. Ensure necessary API keys are correctly set in:"
     # Corrected paths in final instructions
     echo "   - ./.env"
     echo "   - ./settings/llm_settings/ai_models.yml (if modified)"
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
     echo "* Chrome/Chromium and a matching ChromeDriver were installed/checked for Selenium features."
     echo
