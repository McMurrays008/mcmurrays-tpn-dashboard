@echo off
title TPN Dedicated Day - Browse Status Refresh
cd /d "%~dp0"
python refresh_browse_statuses.py
pause
