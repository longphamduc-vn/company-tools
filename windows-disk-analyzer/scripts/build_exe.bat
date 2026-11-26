@echo off
title Build Windows Disk Analyzer EXE
cd /d "%~dp0\.."

set VENV_DIR=.build_venv
if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo Creating isolated build virtual environment...
    python -m venv "%VENV_DIR%"
)

"%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip pyinstaller
if %ERRORLEVEL% NEQ 0 (
    echo Failed to install PyInstaller.
    exit /b 1
)

"%VENV_DIR%\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed --name "WindowsDiskAnalyzer" main.py
if %ERRORLEVEL% EQU 0 (
    echo.
    echo Build succeeded: dist\WindowsDiskAnalyzer.exe
) else (
    echo Build failed.
    exit /b 1
)
