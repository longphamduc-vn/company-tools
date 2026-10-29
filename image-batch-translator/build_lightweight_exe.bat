@echo off
setlocal EnableDelayedExpansion

title Smart Batch Extractor - Lightweight EXE Builder
color 0b

echo =======================================================================
echo     BUILDING LIGHTWEIGHT STANDALONE WINDOWS EXE (.exe)
echo =======================================================================
echo.

cd /d "%~dp0"

:: 1. Check Python installation
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python not found in PATH!
    echo Please install Python 3.9+ from https://www.python.org and add it to PATH.
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version') do set PY_VER=%%i
echo [*] Detected: %PY_VER%

:: 2. Setup isolated clean virtual environment for minimum size
set VENV_DIR=.build_venv
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo.
    echo [*] Creating isolated virtual environment '%VENV_DIR%' to minimize EXE size...
    python -m venv %VENV_DIR%
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to create virtual environment!
        pause
        exit /b 1
    )
)

call "%VENV_DIR%\Scripts\activate.bat"

:: 3. Install strictly required lightweight dependencies
echo.
echo [*] Ensuring minimal lightweight dependencies are installed...
python -m pip install --upgrade pip --quiet
python -m pip install pyinstaller pillow openpyxl chrome-lens-py deep-translator rapidocr-onnxruntime --quiet
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to install dependencies!
    pause
    exit /b 1
)

:: 4. Build with optimized PyInstaller spec
echo.
echo [*] Compiling ultra-lightweight standalone EXE using PyInstaller...
pyinstaller image_batch_translator.spec --clean --noconfirm

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] PyInstaller build failed! Please check the output above.
    pause
    exit /b 1
)

:: 5. Report success & file size
set EXE_PATH=dist\SmartBatchExtractor.exe
if exist "%EXE_PATH%" (
    for %%F in ("%EXE_PATH%") do (
        set /a SIZE_MB=%%~zF / 1048576
        set SIZE_BYTES=%%~zF
    )
    echo.
    echo =======================================================================
    echo  [SUCCESS] Standalone EXE created successfully!
    echo.
    echo  Output file : %CD%\%EXE_PATH%
    echo  Approx. size: !SIZE_MB! MB (!SIZE_BYTES! bytes)
    echo =======================================================================
    echo.
    echo  Tip: You can now copy and run '%EXE_PATH%' on any Windows PC
    echo  without installing Python or any dependencies!
    echo.
) else (
    echo [WARNING] Build completed but '%EXE_PATH%' was not found.
)

pause
