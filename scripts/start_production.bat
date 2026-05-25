@echo off
REM Flower Vending System - Production Startup Script (Windows)
REM This script starts the vending machine with real hardware.

cd /d "%~dp0.."

echo === Flower Vending System - Production Mode ===
echo.

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Install Python 3.11+ from python.org
    pause
    exit /b 1
)

REM Install/update dependencies
echo [1/3] Checking dependencies...
pip install -q pyserial pydantic pyyaml flower-vending-system 2>nul

REM Run discovery
echo [2/3] Discovering hardware...
python -m flower_vending discover

REM Start production runtime
echo.
echo [3/3] Starting production runtime...
echo Press Ctrl+C to stop.
echo.

python -m flower_vending run --config config/machine.production.yaml --no-ui

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Runtime failed. Check logs in var/log/
    pause
    exit /b %errorlevel%
)

pause
