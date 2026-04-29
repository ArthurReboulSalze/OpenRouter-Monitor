@echo off
REM Build script for OpenRouter Monitor (Windows)
REM Creates standalone executable using PyInstaller

echo ========================================
echo OpenRouter Monitor - Build Script
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH
    echo Install Python 3.9+ from python.org
    pause
    exit /b 1
)

REM Check PyInstaller
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo PyInstaller not found. Installing...
    pip install pyinstaller
    if errorlevel 1 (
        echo ERROR: Failed to install PyInstaller
        pause
        exit /b 1
    )
)

REM Install dependencies
echo Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)

REM Clean previous build
echo Cleaning previous build...
if exist "dist" rmdir /s /q dist
if exist "build" rmdir /s /q build
if exist "OpenRouter Monitor.spec" del "OpenRouter Monitor.spec"

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
