@echo off
setlocal enabledelayedexpansion

:: ============================================
:: Ecne AI Podcaster - Qwen3 TTS Installer (Windows)
:: ============================================
:: This installer sets up the Ecne AI Podcaster with Qwen3 TTS as the primary provider.
:: Qwen3 TTS runs natively (no Docker required) and provides high-quality voice synthesis
:: with voice cloning capabilities.
:: ============================================

echo.
echo ============================================
echo    Ecne AI Podcaster - Qwen3 TTS Setup
echo ============================================
echo.
echo  TTS Provider: Qwen3 (RECOMMENDED)
echo  Features: High-quality synthesis + Voice Cloning
echo.
echo ============================================
echo.

:: Get the directory where this batch file is located
set "BATCH_DIR=%~dp0"
cd /d "%BATCH_DIR%"

echo Current directory: %CD%
echo.

:: Check for Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH.
    echo Please install Python 3.8 or higher from https://python.org
    echo.
    pause
    exit /b 1
)

echo [OK] Python found
python --version
echo.

:: Check for Git
git --version >nul 2>&1
if errorlevel 1 (
    echo WARNING: Git is not installed. Some features may not work.
    echo.
) else (
    echo [OK] Git found
    git --version
)
echo.

:: ============================================
:: Setup Host Python Environment
:: ============================================
echo.
echo === Setting Up Host Python Environment ===
echo.

if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created
) else (
    echo [OK] Virtual environment already exists
)

echo.
echo Activating virtual environment...
call venv\Scripts\activate.bat

echo.
echo Upgrading pip...
python -m pip install --upgrade pip

echo.
echo Installing host dependencies...
if exist "requirements_host.txt" (
    pip install -r requirements_host.txt
) else (
    echo Installing core dependencies...
    pip install requests beautifulsoup4 praw pydub python-dotenv pyyaml openai selenium webdriver-manager
)
echo [OK] Host dependencies installed
echo.

:: ============================================
:: Setup Qwen3 TTS Service
:: ============================================
echo.
echo === Setting Up Qwen3 TTS Service ===
echo.

:: Clone Qwen3 TTS API repository if not present
set "QWEN3_REPO=https://github.com/ETomberg391/EcneAI-Qwen-3-TTS-api.git"
set "QWEN3_DIR=EcneAI-Qwen-3-TTS-api"

if not exist "%QWEN3_DIR%" (
    echo Cloning Qwen3 TTS API repository...
    git clone "%QWEN3_REPO%" "%QWEN3_DIR%"
    if errorlevel 1 (
        echo ERROR: Failed to clone repository. Please check your internet connection.
        pause
        exit /b 1
    )
    echo [OK] Repository cloned successfully
) else (
    echo [OK] Qwen3 TTS API directory already exists
    
    :: Check if existing venv is broken and needs recreation
    if exist "%QWEN3_DIR%\venv" (
        echo Checking existing Qwen3 virtual environment...
        :: Try to check if pip works
        call "%QWEN3_DIR%\venv\Scripts\activate.bat" >nul 2>&1
        pip --version >nul 2>&1
        if errorlevel 1 (
            echo WARNING: Qwen3 virtual environment is broken ^(pip not working^)
            echo Removing broken virtual environment...
            rmdir /s /q "%QWEN3_DIR%\venv"
            echo [OK] Broken virtual environment removed
        ) else (
            echo [OK] Qwen3 virtual environment is working
        )
        call "%QWEN3_DIR%\venv\Scripts\deactivate.bat" >nul 2>&1
    )
)
echo.

if exist "setup_qwen3.bat" (
    echo Running Qwen3 setup script...
    call setup_qwen3.bat
    if errorlevel 1 (
        echo ERROR: Qwen3 setup failed
        pause
        exit /b 1
    )
) else (
    echo WARNING: setup_qwen3.bat not found!
    echo Attempting manual Qwen3 setup...
    
    if exist "EcneAI-Qwen-3-TTS-api" (
        cd EcneAI-Qwen-3-TTS-api
        
        if not exist "venv" (
            python -m venv venv
        )
        
        call venv\Scripts\activate.bat
        
        if exist "requirements.txt" (
            pip install -r requirements.txt
        )
        
        cd ..
        echo [OK] Manual Qwen3 setup complete
    ) else (
        echo ERROR: EcneAI-Qwen-3-TTS-api directory not found!
        pause
        exit /b 1
    )
)

echo [OK] Qwen3 service setup complete
echo.

:: ============================================
:: Environment Configuration
:: ============================================
echo.
echo === Environment Configuration ===
echo.

if not exist "settings\.env" (
    echo Creating .env file from template...
    
    if exist "settings\env.example" (
        copy settings\env.example settings\.env
        echo [OK] .env file created from template
    ) else (
        echo Creating minimal .env file...
        (
            echo # TTS Configuration
            echo TTS_PROVIDER=qwen3
            echo QWEN3_PORT=8000
            echo QWEN3_MODEL=Qwen/Qwen3-TTS-12Hz-1.7B-Base
            echo.
            echo # API Keys ^(ADD YOUR OWN^)
            echo OPENAI_API_KEY=your_openai_api_key_here
            echo BRAVE_API_KEY=your_brave_api_key_here
            echo ELEVENLABS_API_KEY=your_elevenlabs_api_key_here
            echo.
            echo # Model Configuration
            echo WHISPER_MODEL=base
            echo DEFAULT_LLM_MODEL=gpt-4o-mini
            echo.
            echo # Paths
            echo CONTENT_DIR=Content_Library
            echo OUTPUT_DIR=Finished_Podcasts
        ) > settings\.env
        echo [OK] Minimal .env file created
    )
) else (
    echo [OK] .env file already exists
)

:: Ensure TTS_PROVIDER is set to qwen3
powershell -Command "(Get-Content settings\.env) -replace 'TTS_PROVIDER=.*', 'TTS_PROVIDER=qwen3' | Set-Content settings\.env"
echo [OK] TTS_PROVIDER set to qwen3 in .env

:: Add Qwen3 config if not present
powershell -Command "if (!(Select-String -Path settings\.env -Pattern 'QWEN3_PORT' -Quiet)) { Add-Content settings\.env '`n# Qwen3 TTS Configuration`nQWEN3_PORT=8000`nQWEN3_MODEL=Qwen/Qwen3-TTS-12Hz-1.7B-Base' }"
echo [OK] Qwen3 configuration added to .env
echo.

:: ============================================
:: Create Directories
:: ============================================
echo.
echo === Creating Directory Structure ===
echo.

if not exist "Content_Library" mkdir Content_Library
if not exist "Finished_Podcasts" mkdir Finished_Podcasts
if not exist "logs" mkdir logs
if not exist "settings\characters" mkdir settings\characters

echo [OK] Directories created
echo.

:: ============================================
:: Create Launcher Scripts
:: ============================================
echo.
echo === Creating Launcher Scripts ===
echo.

:: Main launcher script
(
    echo @echo off
    echo :: Ecne AI Podcaster Launcher
echo :: Starts both the Qwen3 TTS service and the main application
echo.
echo setlocal
echo cd /d "%%~dp0"
echo.
echo echo ============================================
echo echo Starting Ecne AI Podcaster with Qwen3 TTS...
echo echo ============================================
echo.
echo :: Start Qwen3 TTS Service in new window
echo echo Starting Qwen3 TTS Service...
echo start "Qwen3 TTS Service" cmd /k "cd EcneAI-Qwen-3-TTS-api ^&^& call venv\Scripts\activate.bat ^&^& python -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --log-level info"
echo.
echo :: Wait for service to be ready
echo echo Waiting for Qwen3 TTS to be ready...
echo timeout /t 5 /nobreak ^>nul
echo.
echo :: Check if service is running
echo powershell -Command "try { $r = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 2; Write-Host '[OK] Qwen3 TTS is ready!' -ForegroundColor Green } catch { Write-Host '[WARNING] Qwen3 TTS may not be ready yet. Waiting...' -ForegroundColor Yellow }"
echo timeout /t 3 /nobreak ^>nul
echo.
echo :: Launch Control Panel
echo echo Starting Control Panel...
echo call venv\Scripts\activate.bat
echo python control_panel_app.py
echo.
echo echo.
echo echo Control Panel closed.
echo pause
) > launch_podcaster.bat

echo [OK] Created launch_podcaster.bat

:: Quick start script for Qwen3 only
(
    echo @echo off
    echo :: Quick start for Qwen3 TTS service only
    echo cd /d "%%~dp0\EcneAI-Qwen-3-TTS-api"
    echo call venv\Scripts\activate.bat
    echo python -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --log-level info
    echo pause
) > start_qwen3.bat

echo [OK] Created start_qwen3.bat

:: Test script
(
    echo @echo off
    echo :: Test Qwen3 TTS functionality
    echo echo Testing Qwen3 TTS...
    echo echo.
    echo powershell -Command "try { $r = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 3; Write-Host '[OK] Qwen3 TTS service is running' -ForegroundColor Green } catch { Write-Host '[ERROR] Qwen3 TTS service is not running' -ForegroundColor Red; exit 1 }"
    echo echo.
    echo echo Available speakers:
    echo powershell -Command "try { $speakers = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/v1/speakers' -TimeoutSec 5; $speakers.speakers | ForEach-Object { Write-Host ('  - ' + $_.speaker_id + ': ' + $_.name) } } catch { Write-Host '  Could not retrieve speakers' }"
    echo echo.
    echo echo Test complete!
    echo pause
) > test_tts.bat

echo [OK] Created test_tts.bat
echo.

:: ============================================
:: Installation Complete
:: ============================================
echo.
echo ============================================
echo    SETUP COMPLETE! You're ready to go!
echo ============================================
echo.
echo Next Steps:
echo.
echo 1. Start everything:
echo    launch_podcaster.bat
echo.
echo 2. Or start Qwen3 TTS manually:
echo    start_qwen3.bat
echo    Then in another terminal: control_panel_app.py
echo.
echo 3. Test the TTS service:
echo    test_tts.bat
echo.
echo 4. Access the web interface:
echo    http://127.0.0.1:7860 (Control Panel)
echo    http://127.0.0.1:8000/docs (Qwen3 API docs)
echo.
echo Configuration:
echo   - Settings file: settings\.env
echo   - Voice configs: settings\voices\
echo   - Logs: logs\
echo.
echo Voice Options:
echo   Qwen3 has 9 preset speakers: Chelsie, Ryan, Xavier, Ethan,
echo   Anna, Aiden, Chloe, XavierAlt, and Daisy
echo.
echo Happy Podcasting! 
echo.
echo ============================================
echo.

pause
