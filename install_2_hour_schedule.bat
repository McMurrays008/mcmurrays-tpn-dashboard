@echo off
setlocal
title Install TPN Dedicated Day Schedule
cd /d "%~dp0"

set "PY=python"
set "DIR=%~dp0"
set "FULL=%DIR%tpn_dedicated_day_automation.py"
set "STATUS=%DIR%refresh_browse_statuses.py"

echo Creating scheduled tasks...
echo.

schtasks /Create /F /TN "TPN Dedicated Day - Morning Full Refresh" /SC DAILY /ST 08:00 /TR "\"%PY%\" \"%FULL%\"" /IT
if errorlevel 1 goto :error

for %%T in (10:00 12:00 14:00 16:00 18:00) do (
  schtasks /Create /F /TN "TPN Dedicated Day - Status Refresh %%T" /SC DAILY /ST %%T /TR "\"%PY%\" \"%STATUS%\"" /IT
  if errorlevel 1 goto :error
)

echo.
echo Schedule installed:
echo   08:00  Morning Full Refresh
echo   10:00  Browse status refresh
echo   12:00  Browse status refresh
echo   14:00  Browse status refresh
echo   16:00  Browse status refresh
echo   18:00  Browse status refresh
echo.
echo IMPORTANT:
echo These tasks are interactive because TPN may require login.
echo They should run while you are logged into Windows.
pause
exit /b 0

:error
echo.
echo One or more tasks could not be created.
echo Try right-clicking this BAT file and choosing "Run as administrator",
echo or create the same times manually in Windows Task Scheduler.
pause
exit /b 1
