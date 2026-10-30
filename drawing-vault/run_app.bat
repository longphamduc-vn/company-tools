@echo off
setlocal

cd /d "%~dp0"

echo [Drawing Vault] Starting application...

:: Check if conda is available
where conda >nul 2>nul
if %ERRORLEVEL% equ 0 (
    call conda activate company-env 2>nul
)

python main.py %*

if %ERRORLEVEL% neq 0 (
    echo.
    echo Application exited with error code %ERRORLEVEL%.
    pause
)
