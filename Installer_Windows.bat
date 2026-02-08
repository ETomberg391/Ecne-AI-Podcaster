@echo off
setlocal enabledelayedexpansion

:: Get the directory where this batch file is located
set "BATCH_DIR=%~dp0"

:: Change to the batch file's directory to ensure we're in the right location
cd /d "%BATCH_DIR%"

:: Check for Administrator privileges
>nul 2>&1 "%SYSTEMROOT%\system32\cacls.exe" "%SYSTEMROOT%\system32\config\system"

if '%errorlevel%' NEQ '0' (
    echo.
    echo ================================
    echo    ADMINISTRATOR REQUIRED
    echo ================================
    echo.
    echo This installer must be run with Administrator privileges.
    echo.
    echo Right-click on this batch file and select "Run as administrator"
    echo.
    echo Press any key to close...
    pause >nul
    exit /b 1
)

:: If we reach here, we have admin privileges
echo Running Ecne AI Podcaster Windows Installer with Administrator privileges...
echo Current directory: "%CD%"
echo.

:: ============================================
:: TTS Provider Selection
:: ============================================
echo.
echo ============================================
echo    TTS Provider Selection
echo ============================================
echo.
echo Choose your TTS (Text-to-Speech) provider:
echo.
echo   [1] Qwen3 TTS (RECOMMENDED)
echo       - Native Python service (no Docker required)
echo       - High-quality voice synthesis
echo       - Voice cloning capabilities
echo       - 9 preset speakers
echo.
echo   [2] Orpheus TTS (Legacy)
echo       - Docker Desktop required
echo       - More complex installation
echo       - GPU acceleration via Docker
echo.

set /p TTS_CHOICE="Enter your choice [1-2]: "

if "%TTS_CHOICE%"=="1" (
    echo.
    echo Selected: Qwen3 TTS
    echo.
    goto :qwen3_install
) else if "%TTS_CHOICE%"=="2" (
    echo.
    echo Selected: Orpheus TTS
    echo.
    goto :orpheus_install
) else (
    echo.
    echo Invalid choice. Defaulting to Qwen3 TTS (recommended).
    echo.
    goto :qwen3_install
)

:qwen3_install
:: Run the Qwen3 installer
call "%~dp0Installer_Qwen3_Windows.bat"
exit /b %errorlevel%

:orpheus_install
:: Check if PowerShell script exists
if not exist "settings\install\Installer.ps1" (
    echo ERROR: Installer.ps1 not found in settings\install\ directory.
    echo Current directory: "%CD%"
    echo Batch file directory: "%BATCH_DIR%"
    echo Please ensure the installer files are properly organized.
    echo.
    echo Press any key to close...
    pause >nul
    exit /b 1
)

:: Run the PowerShell installer with execution policy bypass from the correct directory
powershell.exe -ExecutionPolicy Bypass -File ".\settings\install\Installer.ps1"

:: Check if PowerShell script completed successfully
if '%errorlevel%' NEQ '0' (
    echo.
    echo Installation completed with errors. Check the output above for details.
    echo.
    echo Press any key to close...
    pause >nul
    exit /b %errorlevel%
)

echo.
echo Installation completed successfully!
echo Press any key to close...
pause >nul
