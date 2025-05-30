#!/bin/bash

# Script to activate virtual environment and run control panel app (Windows version)
# This script works in Git Bash, WSL, or other bash environments on Windows

# Navigate to the script's directory
cd "$(dirname "$0")"

# Check if virtual environment exists
if [ ! -d "host_venv" ]; then
    echo "Error: Virtual environment 'host_venv' not found in current directory."
    echo "Please ensure you're running this script from the project root directory."
    echo "Run the Installer.ps1 script first to set up the environment."
    exit 1
fi

# Check if control_panel_app.py exists
if [ ! -f "control_panel_app.py" ]; then
    echo "Error: control_panel_app.py not found in current directory."
    echo "Please ensure you're running this script from the project root directory."
    exit 1
fi

# Determine the correct activation script based on the environment
VENV_ACTIVATE=""

# Check if we're in WSL (Windows Subsystem for Linux)
if grep -q Microsoft /proc/version 2>/dev/null || grep -q microsoft /proc/version 2>/dev/null; then
    echo "WSL environment detected, using Linux-style activation..."
    VENV_ACTIVATE="host_venv/bin/activate"
# Check if we're in Git Bash or similar Windows bash environment
elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]] || [[ -n "${SYSTEMROOT:-}" ]]; then
    echo "Windows bash environment detected, using Windows-style activation..."
    VENV_ACTIVATE="host_venv/Scripts/activate"
# Default to Linux-style for other environments
else
    echo "Unix-like environment detected, using Linux-style activation..."
    VENV_ACTIVATE="host_venv/bin/activate"
fi

# Check if the activation script exists
if [ ! -f "$VENV_ACTIVATE" ]; then
    echo "Error: Virtual environment activation script not found at: $VENV_ACTIVATE"
    echo "Please ensure the virtual environment was created properly."
    echo "You may need to recreate it by running the Installer.ps1 script."
    exit 1
fi

echo "Activating virtual environment..."
source "$VENV_ACTIVATE"

# Check if activation was successful by verifying Python path
if command -v python >/dev/null 2>&1; then
    PYTHON_PATH=$(which python)
    if [[ "$PYTHON_PATH" == *"host_venv"* ]]; then
        echo "Virtual environment activated successfully."
        echo "Using Python at: $PYTHON_PATH"
    else
        echo "Warning: Virtual environment may not have activated correctly."
        echo "Python path: $PYTHON_PATH"
    fi
else
    echo "Error: Python not found after activation attempt."
    exit 1
fi

echo "Starting Control Panel App..."
echo "================================================================"
echo "The Control Panel will open in your default web browser."
echo "If it doesn't open automatically, navigate to: http://localhost:5000"
echo "Press Ctrl+C to stop the server when you're done."
echo "================================================================"

# Run the control panel app
python control_panel_app.py