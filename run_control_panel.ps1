# PowerShell script to activate virtual environment and run control panel app
# Set error action preference for better error handling
$ErrorActionPreference = "Stop"

# Navigate to the script's directory
Set-Location -Path (Split-Path -Parent $MyInvocation.MyCommand.Path)

# Check if virtual environment exists
if (-not (Test-Path "host_venv")) {
    Write-Host "Error: Virtual environment 'host_venv' not found in current directory." -ForegroundColor Red
    Write-Host "Please ensure you're running this script from the project root directory." -ForegroundColor Red
    Write-Host "Run the Installer.ps1 script first to set up the environment." -ForegroundColor Red
    exit 1
}

# Check if control_panel_app.py exists
if (-not (Test-Path "control_panel_app.py")) {
    Write-Host "Error: control_panel_app.py not found in current directory." -ForegroundColor Red
    Write-Host "Please ensure you're running this script from the project root directory." -ForegroundColor Red
    exit 1
}

# Check if the activation script exists
$activationScript = ".\host_venv\Scripts\Activate.ps1"
if (-not (Test-Path $activationScript)) {
    Write-Host "Error: Virtual environment activation script not found at: $activationScript" -ForegroundColor Red
    Write-Host "Please ensure the virtual environment was created properly." -ForegroundColor Red
    Write-Host "You may need to recreate it by running the Installer.ps1 script." -ForegroundColor Red
    exit 1
}

Write-Host "Activating virtual environment..." -ForegroundColor Green

try {
    # Activate the virtual environment
    & $activationScript
    
    # Verify activation by checking if we can run python from the venv
    $pythonPath = ".\host_venv\Scripts\python.exe"
    if (Test-Path $pythonPath) {
        Write-Host "Virtual environment activated successfully." -ForegroundColor Green
        Write-Host "Using Python at: $pythonPath" -ForegroundColor Green
    } else {
        Write-Host "Warning: Could not verify Python installation in virtual environment." -ForegroundColor Yellow
    }
}
catch {
    Write-Host "Error: Failed to activate virtual environment: $_" -ForegroundColor Red
    exit 1
}

Write-Host "Starting Control Panel App..." -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "The Control Panel will open in your default web browser." -ForegroundColor Yellow
Write-Host "If it doesn't open automatically, navigate to: http://localhost:5000" -ForegroundColor Yellow
Write-Host "Press Ctrl+C to stop the server when you're done." -ForegroundColor Yellow
Write-Host "================================================================" -ForegroundColor Cyan

try {
    # Run the control panel app using the venv python
    & ".\host_venv\Scripts\python.exe" "control_panel_app.py"
}
catch {
    Write-Host "Error running control panel app: $_" -ForegroundColor Red
    exit 1
}