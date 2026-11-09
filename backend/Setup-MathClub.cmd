@echo off
cd /d "%~dp0"
py -3 scripts\setup.py
if errorlevel 1 (
  echo Setup failed. Install Python 3.11 or newer and check the output above.
  pause
  exit /b 1
)
pause
