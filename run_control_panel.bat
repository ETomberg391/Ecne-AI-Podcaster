@echo off
REM Batch script to activate virtual environment and run control panel app
REM This script can be double-clicked in Windows File Explorer

echo ================================================================
echo  Ecne AI Podcaster - Control Panel Launcher
echo ================================================================
echo.

REM Navigate to the script's directory
cd /d "%~dp0"

REM Check if virtual environment exists
if not exist "host_venv" (
    echo Error: Virtual environment 'host_venv' not found in current directory.
    echo Please ensure you're running this script from the project root directory.
    echo Run the Installer.ps1 script first to set up the environment.
    echo.
    pause
    exit /b 1
)

REM Check if control_panel_app.py exists
if not exist "control_panel_app.py" (
    echo Error: control_panel_app.py not found in current directory.
    echo Please ensure you're running this script from the project root directory.
    echo.
    pause
    exit /b 1
)

REM Check if the Python executable exists in the virtual environment
if not exist "host_venv\Scripts\python.exe" (
    echo Error: Python executable not found in virtual environment.
    echo Please ensure the virtual environment was created properly.
    echo You may need to recreate it by running the Installer.ps1 script.
    echo.
    pause
    exit /b 1
)

echo Activating virtual environment...
echo Virtual environment found and ready.
echo.
echo Starting Control Panel App...
echo ================================================================
echo The Control Panel will open in your default web browser.
echo If it doesn't open automatically, navigate to: http://localhost:5000
echo.
echo IMPORTANT: Keep this window open while using the Control Panel.
echo To stop the server, close this window or press Ctrl+C.
echo ================================================================
echo.

REM Run the control panel app using the virtual environment's Python
call "host_venv\Scripts\activate.bat"
python "control_panel_app.py"

REM If we reach here, the app has stopped
echo.
echo Control Panel App has stopped.
echo You can close this window now.
pause