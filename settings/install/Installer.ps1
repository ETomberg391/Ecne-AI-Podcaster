#Requires -Version 5.1

# PowerShell Installer for Orpheus TTS GGUF Setup (Windows 10/11)
# Equivalent of Installer.sh for Windows environments

# Set strict mode for better error handling
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Get the directory where the script is located
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$ORIGINAL_DIR = Get-Location

# --- Configuration ---
$DEFAULT_INSTALL_DIR = "orpheus_tts_setup"
$DEFAULT_LLAMA_SERVER_PORT = "8080"
$DEFAULT_FASTAPI_PORT = "5006"
$MODEL_URL = "https://huggingface.co/lex-au/Orpheus-3b-FT-Q8_0.gguf/resolve/main/Orpheus-3b-FT-Q8_0.gguf?download=true"
$MODEL_FILENAME = "Orpheus-3b-FT-Q8_0.gguf"
$PYTHON_CMD = "python"  # Default, will try to refine
$PIP_CMD = "pip"        # Default, will try to refine
$LLAMA_SERVER_EXE_NAME = "llama-server"
$ORPHEUS_MAX_TOKENS = "8192"

# Attempt to find Python 3.11 specifically
$python311Path = Get-Command python3.11.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
if ($python311Path) {
    $PYTHON_CMD = $python311Path
    $PIP_CMD = Join-Path (Split-Path $python311Path -Parent) "pip.exe"
    Write-Info "Using Python 3.11 from: $PYTHON_CMD"
}
else {
    # If python3.11.exe not found, check the version of the default 'python' command
    try {
        $pythonVersionOutput = & python --version 2>&1
        if ($pythonVersionOutput -match "Python 3\.11\.") {
            Write-Info "Default 'python' command is Python 3.11."
        }
        else {
            Write-Warning "Default 'python' command is not Python 3.11. Found: $pythonVersionOutput. This might cause compatibility issues."
            Write-Warning "Please ensure Python 3.11 is installed and accessible via 'python' or 'python3.11'."
        }
    }
    catch {
        Write-Warning "Could not determine default 'python' version. Ensure Python 3.11 is installed."
    }
}

# --- Helper Functions ---
function Write-Info {
    param([string]$Message)
    Write-Host "INFO: $Message" -ForegroundColor Green
}

function Write-Warning {
    param([string]$Message)
    Write-Host "WARNING: $Message" -ForegroundColor Yellow
}

function Write-Error {
    param([string]$Message)
    Write-Host "ERROR: $Message" -ForegroundColor Red
    exit 1
}

# Function to check if a command exists and optionally install it
function Test-Command {
    param(
        [string]$CommandName,
        [string]$InstallSuggestion = "",
        [string]$PackageName = $CommandName,
        [string]$PackageManager = "",
        [string]$InstallCommand = ""
    )

    if (-not (Get-Command $CommandName -ErrorAction SilentlyContinue)) {
        Write-Warning "Command '$CommandName' not found."
        
        # Only offer to install if we have a package manager and install command
        if ($PackageManager -and $InstallCommand) {
            $install = Read-Host "Do you want to attempt to install '$PackageName' using $PackageManager? [Y/n]"
            $install = $install.ToLower()
            
            if ($install -ne "n") {
                Write-Info "Attempting to install '$PackageName'..."
                try {
                    Invoke-Expression "$InstallCommand $PackageName"
                    Write-Info "'$PackageName' installed successfully."
                    
                    # Verify command is now available
                    if (-not (Get-Command $CommandName -ErrorAction SilentlyContinue)) {
                        Write-Error "Installation of '$PackageName' seemed successful, but command '$CommandName' is still not found. Please check your PATH or the installation."
                    }
                    return $true
                }
                catch {
                    Write-Error "Failed to install '$PackageName' using $PackageManager. $_"
                }
            }
            else {
                $errorMsg = "Command '$CommandName' is required to continue."
                if ($InstallSuggestion) {
                    $errorMsg += " $InstallSuggestion"
                }
                else {
                    $errorMsg += " Please install it first."
                }
                Write-Error $errorMsg
            }
        }
        else {
            $errorMsg = "Command '$CommandName' not found."
            if ($InstallSuggestion) {
                $errorMsg += " $InstallSuggestion"
            }
            else {
                $errorMsg += " Please install it first."
            }
            Write-Error $errorMsg
        }
    }
    return $true
}

# --- Main Script ---
Write-Host "---------------------------------------------"
Write-Host " Orpheus TTS GGUF Setup Script (Windows PowerShell Version) "
Write-Host "---------------------------------------------"
Write-Host ""
Write-Host "=== INSTALLATION OVERVIEW ==="
Write-Host "This installer may install the following components (with your consent):"
Write-Host ""
Write-Host "CORE REQUIREMENTS (automatically prompted if missing):"
Write-Host "  • Git - Version control system"
Write-Host "  • Python 3.11 - Programming language runtime"
Write-Host "  • pip - Python package manager"
Write-Host "  • FFMPEG - Audio/video processing tool"
Write-Host ""
Write-Host "CONTAINERIZATION (required for TTS service):"
Write-Host "  • Docker Desktop - Container platform (~500MB-1GB)"
Write-Host ""
Write-Host "WEB AUTOMATION (required for web scraping):"
Write-Host "  • Google Chrome - Web browser (~100-150MB)"
Write-Host "  • ChromeDriver - Browser automation driver (auto-matched)"
Write-Host ""
Write-Host "DEVELOPMENT TOOLS (optional, improves compatibility):"
Write-Host "  • Visual C++ Build Tools - C++ compiler for Python packages (~3-6GB)"
Write-Host "  • Media Libraries - Enhanced codec support (~50-200MB)"
Write-Host "  • pywin32 - Windows-specific Python extensions (~10-20MB)"
Write-Host ""
Write-Host "PYTHON ENVIRONMENT:"
Write-Host "  • Virtual environment creation (host_venv)"
Write-Host "  • Python packages from requirements_host.txt"
Write-Host "  • NLTK data downloads"
Write-Host ""
Write-Host "Each installation will be presented with detailed information"
Write-Host "and you can choose to accept or decline each component."
Write-Host "---------------------------------------------"
Write-Host ""

# --- OS Detection and Package Manager Setup ---
Write-Info "Detecting Windows version and package manager..."

# Initialize variables
$OS_TYPE = "windows"
$OS_ID = ""
$PKG_MANAGER = ""
$INSTALL_CMD = ""
$CHROME_INSTALLED_VIA_PKG_MANAGER = $false

# Detect Windows version
try {
    $winVersion = [System.Environment]::OSVersion.Version
    $winVersionString = (Get-WmiObject -Class Win32_OperatingSystem).Caption
    
    Write-Info "Detected: $winVersionString"
    
    if ($winVersion.Major -eq 10 -and $winVersion.Build -ge 22000) {
        $OS_ID = "windows11"
        Write-Info "Detected Windows 11"
    }
    elseif ($winVersion.Major -eq 10) {
        $OS_ID = "windows10"
        Write-Info "Detected Windows 10"
    }
    else {
        $OS_ID = "windows"
        Write-Info "Detected Windows (version unknown)"
    }
}
catch {
    $OS_ID = "windows"
    Write-Info "Detected Windows (version detection failed)"
}

# Check for package managers (Winget/Choco)
if (Get-Command winget -ErrorAction SilentlyContinue) {
    $PKG_MANAGER = "winget"
    $INSTALL_CMD = "winget install -e --accept-source-agreements --accept-package-agreements"
    Write-Info "Found winget package manager"
}
elseif (Get-Command choco -ErrorAction SilentlyContinue) {
    $PKG_MANAGER = "choco"
    $INSTALL_CMD = "choco install -y"
    Write-Info "Found Chocolatey package manager"
}
else {
    Write-Warning "No supported package manager found on Windows (winget or chocolatey). Some prerequisites might need manual installation."
}

if ($PKG_MANAGER) {
    Write-Info "Detected Package Manager: $PKG_MANAGER"
}

Write-Host ""

# --- Prerequisites Check ---
Write-Info "Checking prerequisites..."

# Check Git
Test-Command -CommandName "git" -InstallSuggestion "Please install Git from https://git-scm.com/download/win" -PackageName "Git.Git" -PackageManager $PKG_MANAGER -InstallCommand $INSTALL_CMD

Write-Info "Core prerequisites met."

# --- Host Python Script Prerequisites ---
Write-Info "Checking prerequisites for host Python scripts (script_builder.py, orpheus_tts.py)..."

# Check Python
Test-Command -CommandName $PYTHON_CMD -InstallSuggestion "Please install Python from https://python.org/downloads" -PackageName "Python.Python.3.11" -PackageManager $PKG_MANAGER -InstallCommand $INSTALL_CMD

# Check pip (usually comes with Python)
Test-Command -CommandName $PIP_CMD -InstallSuggestion "Pip should come with Python. Please reinstall Python or install pip manually."

# Check ffmpeg
Test-Command -CommandName "ffmpeg" -InstallSuggestion "Please install ffmpeg from https://ffmpeg.org/download.html" -PackageName "Gyan.FFmpeg" -PackageManager $PKG_MANAGER -InstallCommand $INSTALL_CMD

# --- Docker Installation ---
Write-Info "Checking for Docker..."

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Warning "Command 'docker' not found."
    
    if ($PKG_MANAGER -and $INSTALL_CMD) {
        Write-Host ""
        Write-Host "=== Docker Desktop Installation ==="
        Write-Host "PURPOSE: Required to run the Orpheus TTS service containers"
        Write-Host "COMPONENTS: Docker engine, Docker Compose, container runtime"
        Write-Host "REQUIREMENTS: WSL2 (Windows Subsystem for Linux)"
        Write-Host "SIZE: ~500MB-1GB download + installation space"
        Write-Host "NOTE: May require computer restart and WSL2 setup"
        Write-Host ""
        $installDocker = Read-Host "Do you want to install Docker Desktop using '$PKG_MANAGER'? [y/N]"
        $installDocker = $installDocker.ToLower()
        
        if ($installDocker -eq "y") {
            Write-Info "Attempting to install Docker Desktop using $PKG_MANAGER..."
            
            try {
                switch ($PKG_MANAGER) {
                    "winget" {
                        Invoke-Expression "$INSTALL_CMD Docker.DockerDesktop"
                    }
                    "choco" {
                        Invoke-Expression "$INSTALL_CMD docker-desktop"
                    }
                }
                Write-Info "Docker Desktop installation attempt finished successfully."
                Write-Info "IMPORTANT: You may need to restart your computer and enable WSL2 for Docker to work properly."
                Write-Info "Please follow the Docker Desktop setup wizard after installation."
            }
            catch {
                Write-Error "Docker Desktop installation attempt failed. Please install Docker Desktop manually: https://docs.docker.com/desktop/install/windows-install/"
            }
        }
        else {
            Write-Error "Docker is required and was not installed automatically. Please install Docker Desktop manually to continue: https://docs.docker.com/desktop/install/windows-install/"
        }
    }
    else {
        Write-Error "Docker is required but could not be found, and no package manager is available for automatic installation. Please install Docker Desktop manually: https://docs.docker.com/desktop/install/windows-install/"
    }
}
else {
    Write-Info "Docker found."
}

# Check Docker Compose (usually included with Docker Desktop on Windows)
Write-Info "Checking for Docker Compose..."
try {
    docker compose version | Out-Null
    $DOCKER_COMPOSE_CMD = "docker compose"
    Write-Info "Found 'docker compose' (V2 syntax)."
}
catch {
    try {
        docker-compose --version | Out-Null
        $DOCKER_COMPOSE_CMD = "docker-compose"
        Write-Info "Found 'docker-compose' (V1 syntax)."
    }
    catch {
        Write-Error "Docker Compose not found. Please ensure Docker Desktop is properly installed."
    }
}

Write-Host ""

# --- Get User Input ---
$INSTALL_DIR = Read-Host "Enter installation directory [$DEFAULT_INSTALL_DIR]"
if ([string]::IsNullOrWhiteSpace($INSTALL_DIR)) {
    $INSTALL_DIR = $DEFAULT_INSTALL_DIR
}

# Verify running as administrator (batch file should ensure this)
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")

if (-not $isAdmin) {
    Write-Error "This installer must be run as Administrator. Please use the Installer_Windows.bat file which handles privilege elevation."
    exit 1
}
else {
    Write-Info "Running with Administrator privileges."
}

# Check for GPU (NVIDIA on Windows)
$USE_GPU = "n"
try {
    nvidia-smi | Out-Null
    Write-Info "Nvidia GPU detected."
    $USE_GPU = "y"
    
    # On Windows, GPU support for Docker typically comes with Docker Desktop and NVIDIA drivers
    Write-Info "GPU support should be available through Docker Desktop with NVIDIA drivers."
}
catch {
    Write-Info "No NVIDIA GPU detected or nvidia-smi not available."
}

# --- Create Directories ---
Write-Info "Ensuring installation directory exists: $INSTALL_DIR"
if (-not (Test-Path $INSTALL_DIR)) {
    New-Item -ItemType Directory -Path $INSTALL_DIR -Force | Out-Null
}

Set-Location $INSTALL_DIR
$INSTALL_DIR_ABS = Get-Location

# Create Orpheus-FastAPI directory
if (-not (Test-Path "Orpheus-FastAPI")) {
    New-Item -ItemType Directory -Path "Orpheus-FastAPI" -Force | Out-Null
}

# --- Get Orpheus-FastAPI Source Code ---
Write-Info "Ensuring Orpheus-FastAPI source code is present..."
Set-Location "$INSTALL_DIR_ABS\Orpheus-FastAPI"
$FASTAPI_DIR = Get-Location

if (Test-Path ".git") {
    Write-Warning "Orpheus-FastAPI directory already exists, pulling latest."
    try {
        git reset --hard HEAD 2>$null
        git pull origin main 2>$null
        Write-Info "Successfully pulled latest changes for Orpheus-FastAPI."
    }
    catch {
        Write-Warning "Git pull failed for Orpheus-FastAPI. Proceeding with existing files."
    }
}
elseif ((Get-ChildItem -Path . -Force | Measure-Object).Count -eq 0) {
    # Directory is empty, safe to clone
    Write-Info "Cloning Orpheus-FastAPI repository..."
    git clone https://github.com/Lex-au/Orpheus-FastAPI.git .
}
else {
    # Directory is not empty and not a git repo
    Write-Warning "Directory exists and is not empty, but not a git repository. Skipping clone and assuming files are present."
}

Write-Info "Orpheus-FastAPI source code is ready."

# Check if .env exists in the cloned directory
if (-not (Test-Path ".env")) {
    Write-Info "Copying .env.example to .env in Orpheus-FastAPI directory..."
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Info ".env created from .env.example in Orpheus-FastAPI directory."
    }
    else {
        Write-Warning ".env.example not found in Orpheus-FastAPI directory. Cannot create .env."
    }
}
else {
    Write-Warning ".env already exists in Orpheus-FastAPI directory. Skipping copy."
}

Set-Location $ORIGINAL_DIR

# --- .env Configuration (Root Directory) ---
# Since script is now in settings/install/, we need to go up two levels to reach root
$ROOT_PROJECT_DIR = Split-Path (Split-Path $SCRIPT_DIR -Parent) -Parent
$ROOT_ENV_PATH = Join-Path $ROOT_PROJECT_DIR ".env"
$EXAMPLE_ENV_PATH = Join-Path $ROOT_PROJECT_DIR "settings\env.example"

if (-not (Test-Path $ROOT_ENV_PATH)) {
    Write-Info "Copying $EXAMPLE_ENV_PATH to $ROOT_ENV_PATH..."
    Copy-Item $EXAMPLE_ENV_PATH $ROOT_ENV_PATH
}
else {
    Write-Warning "$ROOT_ENV_PATH already exists in root directory. Skipping copy from $EXAMPLE_ENV_PATH."
}

# Determine expected activation script path
$VENV_ACTIVATE = ".\host_venv\Scripts\Activate.ps1"

# --- Setup Host Python Environment ---
Write-Info "Setting up Python virtual environment for host scripts..."

if (-not (Test-Path "host_venv")) {
    Write-Info "Creating Python virtual environment 'host_venv' for host scripts..."
    & $PYTHON_CMD -m venv "host_venv"
}
else {
    Write-Warning "Host virtual environment 'host_venv' already exists. Skipping creation."
    Write-Warning "If you encounter issues, remove the 'host_venv' directory and re-run the script."
}

Write-Info "Activating host virtual environment and installing dependencies from requirements_host.txt..."

# Activate virtual environment and install dependencies
try {
    if (-not (Test-Path $VENV_ACTIVATE)) {
        Write-Error "Virtual environment activation script not found at: $VENV_ACTIVATE"
    }
    
    # Use & to execute the activation script, then install dependencies
    . $VENV_ACTIVATE
    Write-Info "Upgrading pip in host venv..."
    & ".\host_venv\Scripts\python.exe" -m pip install --upgrade pip
    
    $requirementsPath = Join-Path $ROOT_PROJECT_DIR "requirements_host.txt"
    if (Test-Path $requirementsPath) {
        Write-Info "Installing host dependencies from $requirementsPath..."
        & ".\host_venv\Scripts\pip.exe" install -r $requirementsPath
        
        # Check Python version and install audioop-lts if Python 3.13+
        try {
            $pythonVersionOutput = & ".\host_venv\Scripts\python.exe" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            $pythonVersion = [version]$pythonVersionOutput
            
            if ($pythonVersion -ge [version]"3.13") {
                Write-Info "Python $pythonVersionOutput detected. Installing audioop-lts for Python 3.13+ compatibility..."
                & ".\host_venv\Scripts\pip.exe" install audioop-lts
            }
            else {
                Write-Info "Python $pythonVersionOutput detected. Using built-in audioop module (audioop-lts not needed)."
            }
        }
        catch {
            Write-Warning "Could not determine Python version. Skipping audioop-lts installation."
        }
        
        # Download NLTK data
        Write-Info "Downloading NLTK 'punkt' tokenizer data..."
        & ".\host_venv\Scripts\python.exe" -m nltk.downloader punkt
        Write-Info "Downloading NLTK 'punkt_tab' tokenizer data..."
        & ".\host_venv\Scripts\python.exe" -m nltk.downloader punkt_tab
    }
    else {
        Write-Error "Could not find $requirementsPath. Cannot install host dependencies."
    }
}
catch {
    Write-Error "Failed to set up Python virtual environment: $_"
}

Write-Info "Host Python environment setup complete."
Write-Host ""

# --- System Dependencies for Audio/Video Processing ---
Write-Info "Checking system dependencies for audio/video processing..."

# Check and install Visual C++ Build Tools (required for compiling Python packages like audioop-lts)
if ($PKG_MANAGER -and $INSTALL_CMD) {
    Write-Host ""
    Write-Host "=== Visual C++ Build Tools Installation ==="
    Write-Host "PURPOSE: Required for compiling Python packages with C extensions"
    Write-Host "PACKAGES: audioop-lts, scipy, numpy, soundfile, and other audio processing libraries"
    Write-Host "SIZE: ~3-6GB download + installation space"
    Write-Host "NOTE: May require computer restart after installation"
    Write-Host ""
    $installBuildTools = Read-Host "Do you want to install Visual C++ Build Tools? [y/N]"
    $installBuildTools = $installBuildTools.ToLower()
    
    if ($installBuildTools -eq "y") {
        try {
            switch ($PKG_MANAGER) {
                "winget" {
                    Write-Info "Installing Visual C++ Build Tools using winget..."
                    # Install Visual Studio Build Tools which includes MSVC compiler
                    Invoke-Expression "$INSTALL_CMD Microsoft.VisualStudio.2022.BuildTools"
                }
                "choco" {
                    Write-Info "Installing Visual C++ Build Tools using chocolatey..."
                    Invoke-Expression "$INSTALL_CMD visualstudio2022buildtools"
                    # Also install Windows SDK
                    Invoke-Expression "$INSTALL_CMD windows-sdk-10-version-2004-all"
                }
            }
            Write-Info "Visual C++ Build Tools installation completed."
            Write-Warning "You may need to restart your computer for the build tools to be fully available."
        }
        catch {
            Write-Warning "Visual C++ Build Tools installation failed: $_"
            Write-Warning "Some Python packages requiring compilation may fail to install."
        }
    }
    else {
        Write-Warning "Visual C++ Build Tools not installed. Some Python packages may fail to compile."
    }
}

# Check and install additional media libraries
if ($PKG_MANAGER -and $INSTALL_CMD) {
    Write-Host ""
    Write-Host "=== Media Libraries Installation ==="
    Write-Host "PURPOSE: Enhanced codec support for video/audio processing"
    Write-Host "PACKAGES: HEIF/HEVC video extensions (winget) or K-Lite Codec Pack (chocolatey)"
    Write-Host "BENEFITS: Better support for moviepy, pygame, and multimedia formats"
    Write-Host "SIZE: 50-200MB depending on package manager"
    Write-Host ""
    $installMediaLibs = Read-Host "Do you want to install additional media libraries? [y/N]"
    $installMediaLibs = $installMediaLibs.ToLower()
    
    if ($installMediaLibs -eq "y") {
        try {
            switch ($PKG_MANAGER) {
                "winget" {
                    Write-Info "Installing media libraries using winget..."
                    # Install media codecs and libraries that might be useful
                    Invoke-Expression "$INSTALL_CMD 9PMMSR1CGPWG" # HEIF Image Extensions
                    Invoke-Expression "$INSTALL_CMD 9N4WGH0Z6VHQ" # HEVC Video Extensions
                }
                "choco" {
                    Write-Info "Installing media libraries using chocolatey..."
                    # Install K-Lite Codec Pack for comprehensive media support
                    Invoke-Expression "$INSTALL_CMD k-litecodecpackfull"
                }
            }
            Write-Info "Media libraries installation completed."
        }
        catch {
            Write-Warning "Media libraries installation failed: $_"
        }
    }
}

# Install additional Python packages that might help with system integration
Write-Host ""
Write-Host "=== Python Windows Integration Package ==="
Write-Host "PURPOSE: Windows-specific Python extensions for better OS integration"
Write-Host "PACKAGE: pywin32 (Windows API access, COM objects, services)"
Write-Host "BENEFITS: Enhanced file operations, system integration, GUI features"
Write-Host "SIZE: ~10-20MB"
Write-Host ""
$installPywin32 = Read-Host "Do you want to install pywin32 for better Windows integration? [Y/n]"
$installPywin32 = $installPywin32.ToLower()

if ($installPywin32 -ne "n") {
    Write-Info "Installing pywin32..."
    try {
        & ".\host_venv\Scripts\pip.exe" install pywin32
        Write-Info "pywin32 installed successfully (Windows-specific Python extensions)."
    }
    catch {
        Write-Warning "Failed to install pywin32: $_"
    }
}
else {
    Write-Info "Skipping pywin32 installation."
}

# Verify critical Python packages can be imported
Write-Info "Verifying critical Python packages..."
$packagesToTest = @(
    @("soundfile", "Audio file processing"),
    @("pygame", "Audio/Video multimedia"),
    @("PIL", "Image processing (Pillow)"),
    @("matplotlib", "Plotting and visualization"),
    @("selenium", "Web automation"),
    @("nltk", "Natural language processing")
)

foreach ($package in $packagesToTest) {
    $packageName = $package[0]
    $description = $package[1]
    try {
        $testResult = & ".\host_venv\Scripts\python.exe" -c "import $packageName; print('OK')" 2>$null
        if ($testResult -eq "OK") {
            Write-Info "✅ $packageName ($description) - Import successful"
        }
        else {
            Write-Warning "⚠️ $packageName ($description) - Import failed"
        }
    }
    catch {
        Write-Warning "⚠️ $packageName ($description) - Import test failed: $_"
    }
}


# --- Chrome Detection and ChromeDriver Installation ---
$CHROMEDRIVER_PATH = ".\host_venv\Scripts\chromedriver.exe"

# Function to get Chrome version
function Get-ChromeVersion {
    try {
        # Try common Chrome installation paths
        $chromePaths = @(
            "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe",
            "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
            "${env:LOCALAPPDATA}\Google\Chrome\Application\chrome.exe"
        )
        
        foreach ($path in $chromePaths) {
            if (Test-Path $path) {
                $versionInfo = (Get-ItemProperty $path).VersionInfo.ProductVersion
                return $versionInfo
            }
        }
        return $null
    }
    catch {
        return $null
    }
}

# Function to get ChromeDriver version
function Get-ChromeDriverVersion {
    if (Test-Path $CHROMEDRIVER_PATH) {
        try {
            $output = & $CHROMEDRIVER_PATH --version 2>$null
            if ($output -match "ChromeDriver (\d+\.\d+\.\d+\.\d+)") {
                return $matches[1]
            }
        }
        catch {
            return $null
        }
    }
    return $null
}

# Function to download and install ChromeDriver
function Install-ChromeDriver {
    param([string]$ChromeVersion)
    
    try {
        $majorVersion = $ChromeVersion.Split('.')[0]
        Write-Info "Downloading ChromeDriver for Chrome version $majorVersion..."
        
        # Use Chrome for Testing API to get the correct ChromeDriver
        $apiUrl = "https://googlechromelabs.github.io/chrome-for-testing/latest-versions-per-milestone-with-downloads.json"
        $response = Invoke-RestMethod -Uri $apiUrl -ErrorAction Stop
        
        # Get the download URL for the major version
        $downloadUrl = $response.milestones.$majorVersion.downloads.chromedriver |
                      Where-Object { $_.platform -eq "win64" } |
                      Select-Object -ExpandProperty url
        
        if (-not $downloadUrl) {
            Write-Warning "Could not find ChromeDriver download URL for Chrome version $majorVersion"
            return $false
        }
        
        $tempZip = [System.IO.Path]::GetTempFileName() + ".zip"
        $tempExtract = [System.IO.Path]::GetTempPath() + "chromedriver_extract"
        
        Write-Info "Downloading from: $downloadUrl"
        Invoke-WebRequest -Uri $downloadUrl -OutFile $tempZip -ErrorAction Stop
        
        # Clean up and create extraction directory
        if (Test-Path $tempExtract) { Remove-Item $tempExtract -Recurse -Force }
        New-Item -ItemType Directory -Path $tempExtract -Force | Out-Null
        
        # Extract the zip file
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [System.IO.Compression.ZipFile]::ExtractToDirectory($tempZip, $tempExtract)
        
        # Find the chromedriver.exe file (it's usually in a subdirectory)
        $chromedriverExe = Get-ChildItem -Path $tempExtract -Name "chromedriver.exe" -Recurse | Select-Object -First 1
        if (-not $chromedriverExe) {
            Write-Warning "Could not find chromedriver.exe in downloaded archive"
            return $false
        }
        
        $sourcePath = Join-Path $tempExtract $chromedriverExe.FullName.Replace($tempExtract, "").TrimStart('\')
        
        # Ensure the target directory exists
        $targetDir = Split-Path $CHROMEDRIVER_PATH -Parent
        if (-not (Test-Path $targetDir)) {
            New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
        }
        
        # Copy chromedriver to host_venv/Scripts
        Copy-Item $sourcePath $CHROMEDRIVER_PATH -Force
        
        # Clean up temporary files
        Remove-Item $tempZip -Force -ErrorAction SilentlyContinue
        Remove-Item $tempExtract -Recurse -Force -ErrorAction SilentlyContinue
        
        Write-Info "ChromeDriver installed successfully to $CHROMEDRIVER_PATH"
        return $true
    }
    catch {
        Write-Warning "Failed to download/install ChromeDriver: $_"
        return $false
    }
}

Write-Info "Checking for Google Chrome installation..."
$chromeVersion = Get-ChromeVersion

if ($chromeVersion) {
    Write-Info "Found Google Chrome version: $chromeVersion"
    
    # Check if ChromeDriver exists and matches
    $driverVersion = Get-ChromeDriverVersion
    $chromeMajor = $chromeVersion.Split('.')[0]
    
    if ($driverVersion) {
        $driverMajor = $driverVersion.Split('.')[0]
        Write-Info "Found ChromeDriver version: $driverVersion"
        
        if ($chromeMajor -eq $driverMajor) {
            Write-Info "ChromeDriver version matches Chrome. No action needed."
        }
        else {
            Write-Warning "ChromeDriver version mismatch. Installing matching version..."
            Install-ChromeDriver -ChromeVersion $chromeVersion
        }
    }
    else {
        Write-Info "ChromeDriver not found in host_venv. Installing matching version..."
        Install-ChromeDriver -ChromeVersion $chromeVersion
    }
}
else {
    Write-Warning "Google Chrome not found on this system."
    if ($PKG_MANAGER -and $INSTALL_CMD) {
        Write-Host ""
        Write-Host "=== Google Chrome Installation ==="
        Write-Host "PURPOSE: Required for web automation and Selenium features"
        Write-Host "FEATURES: Web scraping, automated browsing, content extraction"
        Write-Host "INCLUDES: Automatic matching ChromeDriver installation"
        Write-Host "SIZE: ~100-150MB download + installation space"
        Write-Host "NOTE: ChromeDriver will be installed to host_venv after Chrome installation"
        Write-Host ""
        $installChrome = Read-Host "Do you want to install Google Chrome using $PKG_MANAGER? [y/N]"
        $installChrome = $installChrome.ToLower()
        
        if ($installChrome -eq "y") {
            try {
                switch ($PKG_MANAGER) {
                    "winget" {
                        Write-Info "Installing Google Chrome using winget..."
                        Invoke-Expression "$INSTALL_CMD Google.Chrome"
                    }
                    "choco" {
                        Write-Info "Installing Google Chrome using chocolatey..."
                        Invoke-Expression "$INSTALL_CMD googlechrome"
                    }
                }
                Write-Info "Chrome installation completed. Checking version..."
                
                # Wait a moment for installation to complete
                Start-Sleep -Seconds 3
                $chromeVersion = Get-ChromeVersion
                
                if ($chromeVersion) {
                    Write-Info "Chrome installed successfully. Version: $chromeVersion"
                    Write-Info "Installing matching ChromeDriver..."
                    Install-ChromeDriver -ChromeVersion $chromeVersion
                }
                else {
                    Write-Warning "Chrome installation may have failed or Chrome not found in expected location."
                }
            }
            catch {
                Write-Warning "Chrome installation failed: $_"
            }
        }
        else {
            Write-Warning "Chrome is required for Selenium features. Please install manually if needed."
        }
    }
    else {
        Write-Warning "No package manager available. Please install Chrome manually for Selenium features."
    }
}

Write-Host ""

# --- Google API Configuration ---
$useGoogleAPI = Read-Host "Do you want to use Google API? The setup is more difficult than setting up Brave API and has a 100/day searching limit (y/N)"
$useGoogleAPI = $useGoogleAPI.ToLower()

if ($useGoogleAPI -eq "y") {
    Write-Host "Get API Key from Google Cloud Console (Credentials page)"
    $googleAPIKey = Read-Host "Enter GOOGLE_API_KEY"
    Write-Host "Get Search Engine ID (cx) from Programmable Search Engine control panel (make sure 'Search entire web' is ON)"
    $googleCSEID = Read-Host "Enter GOOGLE_CSE_ID"
    
    # Update .env with Google API keys
    $envContent = Get-Content $ROOT_ENV_PATH
    $envContent = $envContent -replace '^GOOGLE_API_KEY=.*', "GOOGLE_API_KEY=`"$googleAPIKey`""
    $envContent = $envContent -replace '^GOOGLE_CSE_ID=.*', "GOOGLE_CSE_ID=`"$googleCSEID`""
    $envContent | Set-Content $ROOT_ENV_PATH
}

# --- Brave API Configuration ---
$useBraveAPI = Read-Host "Do you want to enter the Brave API key? (Y/n)"
$useBraveAPI = $useBraveAPI.ToLower()

if ($useBraveAPI -ne "n") {
    Write-Host "Brave Search API Key (Get from https://api.search.brave.com/)"
    $braveAPIKey = Read-Host "BRAVE_API_KEY"
    
    # Update .env with Brave API key
    $envContent = Get-Content $ROOT_ENV_PATH
    $envContent = $envContent -replace '^BRAVE_API_KEY=.*', "BRAVE_API_KEY=`"$braveAPIKey`""
    $envContent | Set-Content $ROOT_ENV_PATH
}

# --- ai_models.yml Configuration ---
$AI_MODELS_YML_PATH = Join-Path $ROOT_PROJECT_DIR "settings\llm_settings\ai_models.yml"
$EXAMPLE_AI_MODELS_YML_PATH = Join-Path $ROOT_PROJECT_DIR "settings\llm_settings\example_ai_models.yml"

if (-not (Test-Path $AI_MODELS_YML_PATH)) {
    Write-Info "Copying $EXAMPLE_AI_MODELS_YML_PATH to $AI_MODELS_YML_PATH..."
    $parentDir = Split-Path $AI_MODELS_YML_PATH -Parent
    if (-not (Test-Path $parentDir)) {
        New-Item -ItemType Directory -Path $parentDir -Force | Out-Null
    }
    
    if (Test-Path $EXAMPLE_AI_MODELS_YML_PATH) {
        Copy-Item $EXAMPLE_AI_MODELS_YML_PATH $AI_MODELS_YML_PATH
        Write-Info "$AI_MODELS_YML_PATH created from example."
    }
    else {
        Write-Error "Example AI models file not found: $EXAMPLE_AI_MODELS_YML_PATH. Cannot proceed."
    }
}
else {
    Write-Warning "$AI_MODELS_YML_PATH already exists. Skipping copy from example."
}

# --- Gemini API Configuration ---
$useGemini = Read-Host "Do you want to use the recommended free Google Gemini 2.0 Flash Exp model with this project? (Y/n)"
$useGemini = $useGemini.ToLower()

if ($useGemini -ne "n") {
    Write-Host "You can get a Google Gemini API key from https://ai.google.dev/gemini-api/docs/api-key"
    $geminiAPIKey = Read-Host "Enter api_key"
    
    # Update ai_models.yml with Gemini API key
    $aiModelsContent = Get-Content $AI_MODELS_YML_PATH
    $aiModelsContent = $aiModelsContent -replace 'api_key: ""', "api_key: `"$geminiAPIKey`""
    $aiModelsContent | Set-Content $AI_MODELS_YML_PATH
    
    # Update .env with DEFAULT_MODEL_CONFIG
    $envContent = Get-Content $ROOT_ENV_PATH
    $envContent = $envContent -replace '^DEFAULT_MODEL_CONFIG=.*', 'DEFAULT_MODEL_CONFIG="gemini_flash"'
    $envContent | Set-Content $ROOT_ENV_PATH
}
else {
    # --- OpenAI API Configuration ---
    Write-Host "Please enter the OpenAI API compatible server settings:"
    $openaiEndpoint = Read-Host "api_endpoint"
    $openaiAPIKey = Read-Host "api_key"
    $openaiModel = Read-Host "model (default ChatGPT4o if nothing entered)"
    if ([string]::IsNullOrWhiteSpace($openaiModel)) {
        $openaiModel = "ChatGPT4o"
    }
    $openaiTemp = Read-Host "temperature (Default 0.7 if nothing entered)"
    if ([string]::IsNullOrWhiteSpace($openaiTemp)) {
        $openaiTemp = "0.7"
    }
    
    # Update ai_models.yml with OpenAI API settings
    $aiModelsContent = Get-Content $AI_MODELS_YML_PATH
    $aiModelsContent = $aiModelsContent -replace 'api_endpoint: ""', "api_endpoint: `"$openaiEndpoint`""
    $aiModelsContent = $aiModelsContent -replace 'api_key: "sk1-example"', "api_key: `"$openaiAPIKey`""
    $aiModelsContent = $aiModelsContent -replace 'model: "QwQ-32B_Example"', "model: `"$openaiModel`""
    $aiModelsContent = $aiModelsContent -replace 'temperature: 0.7', "temperature: $openaiTemp"
    $aiModelsContent | Set-Content $AI_MODELS_YML_PATH
    
    # Update .env with DEFAULT_MODEL_CONFIG
    $envContent = Get-Content $ROOT_ENV_PATH
    $envContent = $envContent -replace '^DEFAULT_MODEL_CONFIG=.*', 'DEFAULT_MODEL_CONFIG="default_model"'
    $envContent | Set-Content $ROOT_ENV_PATH
}

# --- Final Instructions ---
Write-Host ""
Write-Host "---------------------------------------------"
Write-Host " Setup Complete! "
Write-Host "---------------------------------------------"
Write-Host ""
Write-Host "The necessary source code for Orpheus-FastAPI has been cloned/updated into:"
Write-Host "  $FASTAPI_DIR"
Write-Host ""

Write-Host "Next Steps:"
Write-Host ""

Write-Host "1. Start the services using Docker Compose:"
Write-Host "   cd `"$FASTAPI_DIR`""
Write-Host "   $DOCKER_COMPOSE_CMD -f docker-compose-gpu.yml up"
Write-Host "   (Add '-d' to run in detached mode: $DOCKER_COMPOSE_CMD -f docker-compose-gpu.yml up -d)"
Write-Host ""

Write-Host "2. Access the Web UI:"
Write-Host "   Once the containers are running, access the UI in your browser at:"
Write-Host "   http://127.0.0.1:5005"
Write-Host ""

Write-Host "3. To stop the services:"
Write-Host "   Press Ctrl+C in the terminal where compose is running, or if detached:"
Write-Host "   $DOCKER_COMPOSE_CMD -f docker-compose-gpu.yml down"
Write-Host ""

Write-Host "4. To run the host Python scripts (script_builder.py, orpheus_tts.py):"
Write-Host "   - Open a NEW PowerShell window in the BASE directory (where this installer script and the Python scripts are located)."
Write-Host "   - Activate the host virtual environment:"
Write-Host "     .\host_venv\Scripts\Activate.ps1"
Write-Host "   - Run the desired script (e.g.):"
Write-Host "     python `"$ROOT_PROJECT_DIR\script_builder.py`" --topic `"Your Topic Here`" --keywords `"keyword1,keyword2`""
Write-Host "     # or"
Write-Host "     python `"$ROOT_PROJECT_DIR\orpheus_tts.py`" --script podcast_script_final.txt --dev"
Write-Host ""
Write-Host "   - Deactivate the environment when finished: deactivate"
Write-Host ""

Write-Host "5. Ensure necessary API keys are correctly set in:"
Write-Host "   - .\.env"
Write-Host "   - .\settings\llm_settings\ai_models.yml (if modified)"
Write-Host ""

Write-Host "--- Important Notes ---"
if ($USE_GPU -eq "y") {
    Write-Host "* Ensure Docker Desktop is configured correctly with NVIDIA GPU support."
    Write-Host "* The 'docker-compose-gpu.yml' file is configured for GPU usage."
}
else {
    Write-Host "* No NVIDIA GPU detected. The 'docker-compose-gpu.yml' might still attempt to use GPU resources."
    Write-Host "  You might need to use or create a CPU-specific compose file (e.g., 'docker-compose-cpu.yml') if GPU is unavailable."
}
Write-Host "* All components (FastAPI app, llama.cpp server, model) are managed by Docker Compose."
Write-Host "* Chrome and ChromeDriver were installed/checked for Selenium features."
Write-Host "* If Docker Desktop was just installed, you may need to restart your computer."
Write-Host ""