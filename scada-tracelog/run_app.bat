@echo off
title SCADA-TraceLog
cd /d "%~dp0"
python main.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo An error occurred while launching SCADA-TraceLog.
    pause
)
