@echo off
schtasks /Delete /F /TN "TPN Dedicated Day - Morning Full Refresh"
for %%T in (10:00 12:00 14:00 16:00 18:00) do schtasks /Delete /F /TN "TPN Dedicated Day - Status Refresh %%T"
echo.
echo TPN Dedicated Day scheduled tasks removed.
pause
