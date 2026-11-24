@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Please run setup.bat first. See README.md for Python and FFmpeg setup.
    pause
    exit /b 1
)
set PYTHONUTF8=1
".venv\Scripts\python.exe" main.py
if errorlevel 1 (
    echo The application could not start. See the message above and README.md.
    pause
    exit /b 1
)
