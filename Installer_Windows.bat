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
echo Running Orpheus TTS Windows Installer with Administrator privileges...
echo Current directory: %CD%
echo.

:: Check if PowerShell script exists
if not exist "Installer.ps1" (
    echo ERROR: Installer.ps1 not found in the current directory.
    echo Current directory: %CD%
    echo Batch file directory: %BATCH_DIR%
    echo Please ensure this batch file is in the same directory as Installer.ps1
    echo.
    echo Press any key to close...
    pause >nul
    exit /b 1
)

:: Run the PowerShell installer with execution policy bypass from the correct directory
powershell.exe -ExecutionPolicy Bypass -File "%BATCH_DIR%Installer.ps1"

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
