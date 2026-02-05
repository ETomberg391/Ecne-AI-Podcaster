@echo off
setlocal enabledelayedexpansion

:: Qwen3 TTS Setup Script for Windows
:: This script sets up the EcneAI-Qwen-3-TTS-api service

echo ==========================================
echo   Qwen3 TTS API Setup for Windows
echo ==========================================
echo.

:: Get script directory
set "SCRIPT_DIR=%~dp0"
set "QWEN3_DIR=%SCRIPT_DIR%EcneAI-Qwen-3-TTS-api"
set "PYTHON_CMD=python"

echo [INFO] Script directory: %SCRIPT_DIR%
echo [INFO] Qwen3 directory: %QWEN3_DIR%

:: Check if Qwen3 directory exists
if not exist "%QWEN3_DIR%" (
    echo [ERROR] Qwen3 TTS API directory not found at: %QWEN3_DIR%
    echo [INFO] Please ensure the EcneAI-Qwen-3-TTS-api folder exists.
    echo [INFO] You can clone it with: git clone https://github.com/ETomberg391/EcneAI-Qwen-3-TTS-api.git
    pause
    exit /b 1
)

echo [SUCCESS] Found Qwen3 TTS API
echo.

:: Check Python version
%PYTHON_CMD% --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.8 or higher.
    pause
    exit /b 1
)

for /f "tokens=2" %%a in ('%PYTHON_CMD% --version') do set PYTHON_VERSION=%%a
echo [INFO] Python version: %PYTHON_VERSION%
echo.

:: Check for CUDA (simplified check)
echo [INFO] Checking for NVIDIA GPU...
nvidia-smi >nul 2>&1
if errorlevel 1 (
    echo [WARNING] No NVIDIA GPU detected or nvidia-smi not found.
    echo [WARNING] Will use CPU (slower).
    set USE_GPU=false
) else (
    echo [SUCCESS] NVIDIA GPU detected:
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
    set USE_GPU=true
)
echo.

:: Navigate to Qwen3 directory
cd /d "%QWEN3_DIR%"

:: Create virtual environment if it doesn't exist
if not exist "venv" (
    echo [INFO] Creating virtual environment...
    %PYTHON_CMD% -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment
        pause
        exit /b 1
    )
)

:: Activate virtual environment
echo [INFO] Activating virtual environment...
call venv\Scripts\activate.bat

:: Upgrade pip
echo [INFO] Upgrading pip...
python -m pip install --upgrade pip setuptools wheel

:: Install PyTorch based on GPU availability
if "%USE_GPU%"=="true" (
    echo [INFO] Installing PyTorch with CUDA support...
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
) else (
    echo [INFO] Installing PyTorch (CPU only)...
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
)

:: Install Qwen3 TTS requirements
if exist "requirements.txt" (
    echo [INFO] Installing Qwen3 TTS requirements...
    pip install -r requirements.txt
) else (
    echo [ERROR] requirements.txt not found in %QWEN3_DIR%
    pause
    exit /b 1
)

:: Install onnxruntime-gpu if using GPU
if "%USE_GPU%"=="true" (
    echo [INFO] Installing ONNX Runtime GPU...
    pip uninstall -y onnxruntime
    pip install onnxruntime-gpu
)

echo.
echo [SUCCESS] Qwen3 TTS API setup complete!
echo.

:: Create startup script
cd /d "%SCRIPT_DIR%"
(
echo @echo off
echo :: Start Qwen3 TTS API Server
echo.
echo set "SCRIPT_DIR=%%~dp0"
echo set "QWEN3_DIR=%%SCRIPT_DIR%%EcneAI-Qwen-3-TTS-api"
echo.
echo cd /d "%%QWEN3_DIR%%"
echo call venv\Scripts\activate.bat
echo.
echo echo Starting Qwen3 TTS API Server...
echo echo API will be available at: http://127.0.0.1:8000
echo echo Press Ctrl+C to stop
echo echo.
echo.
echo python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
echo.
echo pause
) > start_qwen3.bat

echo [SUCCESS] Created startup script: start_qwen3.bat
echo.

:: Create test script
(
echo @echo off
echo :: Test Qwen3 TTS API
echo.
echo set API_URL=http://127.0.0.1:8000
echo.
echo echo Testing Qwen3 TTS API at %%API_URL%%...
echo echo.
echo.
echo echo 1. Health Check:
echo curl -s %%API_URL%%/health
echo echo.
echo.
echo echo 2. Testing TTS with Ryan voice:
echo curl -s -X POST "%%API_URL%%/v1/audio/speech" ^
echo   -F "model=qwen3-tts-1.7b-customvoice" ^
echo   -F "input=Hello, this is a test of the Qwen3 text to speech system." ^
echo   -F "voice=Ryan" ^
echo   -F "response_format=wav" ^
echo   -F "speed=1.0" ^
echo   --output %%TEMP%%\qwen3_test.wav
echo.
echo if exist "%%TEMP%%\qwen3_test.wav" ^(
echo     echo [SUCCESS] Audio generated: %%TEMP%%\qwen3_test.wav
echo     dir "%%TEMP%%\qwen3_test.wav"
echo ^) else ^(
echo     echo [ERROR] Failed to generate audio
echo ^)
echo.
echo echo.
echo echo Test complete!
echo pause
) > test_qwen3.bat

echo [SUCCESS] Created test script: test_qwen3.bat
echo.

:: Summary
echo ==========================================
echo   Qwen3 TTS Setup Complete!
echo ==========================================
echo.
echo Next Steps:
echo.
echo 1. Start the Qwen3 TTS server:
echo    start_qwen3.bat
echo.
echo 2. In a new terminal, test the API:
echo    test_qwen3.bat
echo.
echo 3. Update your .env file:
echo    Set TTS_PROVIDER=qwen3
echo.
echo 4. Use Qwen3 voices in your podcasts:
echo    python script_builder.py --script your_script.txt --host-voice Ryan --guest-voice Serena
echo.
echo Available Qwen3 Voices:
echo   Male: Ryan, Aiden (English), Dylan, Uncle_Fu, Eric (Chinese)
echo   Female: Serena, Vivian (Chinese/English), Sohee (Korean), Ono_Anna (Japanese)
echo.
echo For voice cloning, use the API directly:
echo   curl -X POST http://localhost:8000/v1/voices ^
echo     -F "name=My Voice" ^
echo     -F "voice_sample=@sample.wav" ^
echo     -F "voice_sample_text=Original text"
echo.

pause
