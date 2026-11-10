@echo off
title Python Step Recorder
cd /d "%~dp0"
python run.py %*
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ========================================================
    echo Error occurred while running Python Step Recorder.
    echo Please make sure dependencies are installed:
    echo    pip install -r requirements.txt
    echo ========================================================
    pause
)

