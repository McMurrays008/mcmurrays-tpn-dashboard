@echo off
title Install TPN Dedicated Day Automation
cd /d "%~dp0"
python -m pip install --upgrade pip
python -m pip install playwright openpyxl
python -m playwright install chromium
echo.
echo Installation complete.
pause
