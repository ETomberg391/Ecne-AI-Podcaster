# Analysis of orpheus_Installer.sh

This document outlines the components, prerequisites, and setup steps performed or guided by the `orpheus_Installer.sh` script.

## 1. System Program Prerequisites (Checks)

The script checks if the following command-line programs are installed before proceeding. If not found, it typically suggests an installation command (often using `apt`) or provides a link to installation instructions.

*   **`git`**: Required for cloning the necessary GitHub repository.
*   **`docker`**: Required for running the core application components in containers.
*   **`docker-compose`** (or `docker compose`): Required for orchestrating the Docker containers defined in the compose file.
*   **`python3`**: The Python 3 interpreter needed for the host virtual environment setup and potentially running helper scripts. (Checked using `command -v python3`).
*   **`pip3`**: The Python package installer for Python 3, used within the host virtual environment. (Checked using `command -v pip3`).
*   **`ffmpeg`**: A multimedia framework, likely needed for audio processing by the TTS system or related scripts.


### Optional Automatic Dependency Installation

*   The script attempts to detect your Linux distribution (Debian/Ubuntu, Arch, Fedora/RHEL, openSUSE families, and derivatives like Mint, Pop!_OS, EndeavourOS, etc. are supported).
*   If detected, it will list recommended system libraries (like `ffmpeg`, `python3-tk`, etc.) needed for the *host* Python scripts.
*   It will then ask if you want to attempt installing these using the system's package manager (`apt`, `pacman`, `dnf`/`yum`) via `sudo`.
*   Answering 'y' (Yes) will trigger the installation attempt. Answering 'n' (No) or pressing Enter (default) will skip this step, requiring manual installation if needed.

### Optional/Recommended System Libraries (Warnings)

The script warns that the *host* Python scripts (`mainv3.py`, `orpheus_tts.py`) might require additional system libraries, suggesting installation commands:

*   `python3-tk` (for Tkinter GUI elements)
*   `libsndfile1` (for audio file handling)
*   `portaudio19-dev` (for audio I/O)
*   Selenium WebDriver (requires a browser like Chrome and its corresponding `chromedriver` in the system PATH) - *Note: The script does NOT install these, only warns about them.*

### GPU-Specific Checks

*   **`nvidia-smi`**: Used to detect if an NVIDIA GPU is present.
*   **`nvidia-container-runtime` / `nvidia-container-toolkit`**: Checks for the necessary toolkit to allow Docker containers to access the NVIDIA GPU.

## 2. GitHub Projects

The script clones or updates the following repository:

*   **Repository:** `https://github.com/Lex-au/Orpheus-FastAPI.git`
*   **Destination:** Cloned into the `Orpheus-FastAPI` subdirectory within the user-specified installation directory (default: `orpheus_tts_setup`).

## 3. Python Virtual Environment (`venv`)

The script sets up a dedicated Python virtual environment for host-level scripts:

*   **Type:** Standard Python `venv`.
*   **Name:** `host_venv`
*   **Location:** Created inside the main installation directory (e.g., `orpheus_tts_setup/host_venv`).
*   **Purpose:** To install Python dependencies for `mainv3.py` and `orpheus_tts.py` without interfering with the system's global Python environment.

## 4. Pip Packages

Python packages are installed using `pip3` *within* the `host_venv` virtual environment:

*   **Source:** Packages listed in the `requirements_host.txt` file (expected to be in the directory *parent* to the installation directory).
*   **Action:** `pip3 install -r ../requirements_host.txt` is executed within the activated `host_venv`.
*   **Specific Packages:** The exact packages depend on the contents of `requirements_host.txt` (not included in the installer script itself).
*   **NLTK Data:** Downloads the 'punkt' tokenizer data (`python3 -m nltk.downloader punkt`) required by the NLTK library (which is presumably listed in `requirements_host.txt`).
*   **Pip Upgrade:** Upgrades `pip` itself within the `host_venv`.

## 5. Docker Components (User Action Required Post-Script)

The script itself **does not** build or run Docker containers. It prepares the necessary files and instructs the user on how to start the services using Docker Compose.

*   **Configuration File:** The primary file used is `docker-compose-gpu.yml` located inside the cloned `Orpheus-FastAPI` directory.
*   **User Command:** The user is instructed to run `docker compose -f docker-compose-gpu.yml up` (or `docker-compose ...` for V1 syntax).
*   **Expected Services (Based on Compose File):**
    *   A FastAPI web application container (likely built from `Dockerfile.gpu` or `Dockerfile.cpu` in the `Orpheus-FastAPI` repo).
    *   A `llama.cpp` server container (likely pulled from a registry or built, responsible for running the GGUF model).
*   **Model Management:** The script defines the URL and filename for the `Orpheus-3b-FT-Q8_0.gguf` model, but the download is likely handled *within* the Docker environment orchestrated by the compose file, not directly by the installer script. The script notes the model is "managed by Docker Compose".
*   **GPU vs CPU:** The script checks for GPU capabilities and defaults to instructing the user to use `docker-compose-gpu.yml`. It warns that a CPU-specific compose file might be needed if no GPU is available or configured correctly with the NVIDIA Container Toolkit.

## 6. Conda Environments

The script does **not** use or create any Conda environments.
