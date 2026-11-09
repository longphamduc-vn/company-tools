@echo off
title Outlook Rule Companion
cd /d "%~dp0"
python main.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo An error occurred while launching Outlook Rule Companion.
    pause
)

