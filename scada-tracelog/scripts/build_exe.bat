@echo off
title SCADA-TraceLog - Standalone Executable Builder
echo ========================================================
echo Building SCADA-TraceLog Standalone Windows Executable (.exe)
echo ========================================================
echo.

:: Kiem tra va cai dat PyInstaller
python -m pip install pyinstaller

echo.
echo Compiling project with PyInstaller...
pyinstaller --noconfirm --onedir --windowed ^
    --name "SCADA-TraceLog" ^
    --add-data "samples;samples" ^
    main.py

echo.
if %ERRORLEVEL% EQU 0 (
    echo ========================================================
    echo Build Successful!
    echo Executable located at: dist\SCADA-TraceLog\SCADA-TraceLog.exe
    echo ========================================================
) else (
    echo Build failed with error code %ERRORLEVEL%.
)
pause
