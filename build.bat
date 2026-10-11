@echo off
REM Build script for OpenRouter Monitor (Windows)
REM Creates standalone executable using PyInstaller

cd /d "%~dp0"
if errorlevel 1 exit /b 1

echo ========================================
echo OpenRouter Monitor - Build Script
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH
    echo Install Python 3.10+ from python.org
    pause
    exit /b 1
)

REM Check PyInstaller
python -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo PyInstaller not found. Installing...
    python -m pip install pyinstaller
    if errorlevel 1 (
        echo ERROR: Failed to install PyInstaller
        pause
        exit /b 1
    )
)

REM Install dependencies
echo Installing dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)

REM Build
echo Building executable...
python build.py
if errorlevel 1 (
    echo ERROR: Build failed
    pause
    exit /b 1
)

echo.
echo ========================================
echo Build successful!
echo Executable: dist\OpenRouter Monitor.exe
echo ========================================
echo.
echo To create installer, open installer.iss in Inno Setup and compile.
echo.

pause
