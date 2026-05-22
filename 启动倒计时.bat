@echo off
chcp 65001 >nul
title 倒计时小工具

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Check & install Pillow
python -c "from PIL import Image" >nul 2>&1
if %errorlevel% neq 0 (
    echo [提示] 正在安装依赖 Pillow...
    pip install Pillow
)

:: Launch
python "%~dp0countdown_widget.py"
