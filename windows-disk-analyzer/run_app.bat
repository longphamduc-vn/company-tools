@echo off
title Windows Disk Analyzer
cd /d "%~dp0"
python main.py %*
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo An error occurred while launching Windows Disk Analyzer.
    pause
)
