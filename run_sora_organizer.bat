@echo off
title SORA Video Organizer
color 0A
echo.
echo  Checking dependencies...
echo.

pip show flask >nul 2>&1
if errorlevel 1 ( echo  Installing Flask... && pip install flask )

pip show google-generativeai >nul 2>&1
if errorlevel 1 ( echo  Installing Google Generative AI... && pip install google-generativeai )

echo.
echo  Starting SORA Organizer...
echo.
python "%~dp0sora_organizer_desktop.py"

if errorlevel 1 (
    echo.
    echo  ERROR: Could not start.
    echo  Make sure Python is installed: https://python.org
    pause
)
