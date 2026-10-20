@echo off
title Running SCADA-TraceLog Test Suite
echo Running automated unit tests...
python -m unittest discover tests
echo.
pause
