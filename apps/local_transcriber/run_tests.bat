@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run setup.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
if errorlevel 1 exit /b 1
set QT_QPA_PLATFORM=offscreen
".venv\Scripts\python.exe" -m pytest tests -q
set TEST_RESULT=%ERRORLEVEL%
pause
exit /b %TEST_RESULT%
