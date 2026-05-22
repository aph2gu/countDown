@echo off
title Countdown Widget

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [Error] Python not found. Please install Python 3.
    echo Download: https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Check & install Pillow
python -c "from PIL import Image" >nul 2>&1
if %errorlevel% neq 0 (
    echo [Info] Installing dependency Pillow...
    pip install Pillow
)

:: Launch the widget WITHOUT a console window
start "" pythonw "%~dp0countdown_widget.py"