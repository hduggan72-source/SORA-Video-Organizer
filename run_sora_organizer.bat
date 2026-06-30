@echo off
title SORA Video Organizer
color 0A
echo.
echo ================================================
echo  SORA Video Organizer - Starting Up
echo ================================================
echo.
echo Checking dependencies...
echo.

pip show flask >nul 2>&1
if errorlevel 1 (
    echo Installing Flask...
    pip install flask
)

pip show opencv-python >nul 2>&1
if errorlevel 1 (
    echo Installing OpenCV for video frame extraction...
    pip install opencv-python
)

pip show anthropic >nul 2>&1
if errorlevel 1 (
    echo Installing Anthropic for Claude AI...
    pip install anthropic
)

echo.
echo All dependencies ready.
echo Starting SORA Organizer...
echo.

python "%~dp0sora_organizer_desktop.py"

echo.
if errorlevel 1 (
    echo ================================================
    echo  ERROR: The organizer crashed.
    echo  Read the message above to diagnose.
    echo ================================================
) else (
    echo Organizer closed normally.
)
echo.
pause
