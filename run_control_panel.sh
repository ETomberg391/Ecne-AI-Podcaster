#!/bin/bash

# Script to activate virtual environment and run control panel app
# Navigate to the script's directory
cd "$(dirname "$0")"

# Check if virtual environment exists
if [ ! -d "host_venv" ]; then
    echo "Error: Virtual environment 'host_venv' not found in current directory."
    echo "Please ensure you're running this script from the project root directory."
    exit 1
fi

# Check if control_panel_app.py exists
if [ ! -f "control_panel_app.py" ]; then
    echo "Error: control_panel_app.py not found in current directory."
    echo "Please ensure you're running this script from the project root directory."
    exit 1
fi

echo "Activating virtual environment..."
source host_venv/bin/activate

# Check if activation was successful
if [ $? -ne 0 ]; then
    echo "Error: Failed to activate virtual environment."
    exit 1
fi

echo "Virtual environment activated successfully."
echo "Starting Control Panel App..."
echo "================================================================"

# Function to open URL in default browser
open_url() {
    local url="http://127.0.0.1:5000"
    echo "Attempting to open $url in your default browser..."
    case "$(uname -s)" in
        Linux*)  xdg-open "$url" >/dev/null 2>&1 & ;;
        Darwin*) open "$url" & ;;
        *)       echo "Please open your browser and navigate to $url" ;;
    esac
}

# Open the browser in the background after a short delay
(sleep 2 && open_url) &

# Run the control panel app in the foreground
python control_panel_app.py