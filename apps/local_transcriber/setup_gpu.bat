@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run setup.bat first, then run setup_gpu.bat.
    pause
    exit /b 1
)
set PYTHONUTF8=1
".venv\Scripts\python.exe" setup_gpu.py
set GPU_SETUP_RESULT=%ERRORLEVEL%
pause
exit /b %GPU_SETUP_RESULT%
