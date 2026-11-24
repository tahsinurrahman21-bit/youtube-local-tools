@echo off
setlocal
cd /d "%~dp0"
echo Setting up this application's private Python environment...
if exist ".venv\Scripts\python.exe" goto install
where py >nul 2>nul
if not errorlevel 1 (
    py -3.11 -m venv .venv
    if not errorlevel 1 goto install
    py -3.12 -m venv .venv
    if not errorlevel 1 goto install
    py -3.13 -m venv .venv
    if not errorlevel 1 goto install
)
where python >nul 2>nul
if errorlevel 1 goto missing
python -m venv .venv
if errorlevel 1 goto missing
:install
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo.
echo Python packages are ready. Install FFmpeg and Deno as described in README.md.
echo Then double-click run.bat. GPU setup is optional for transcription.
pause
exit /b 0
:missing
echo.
echo Python was not found or could not create an environment.
echo Install 64-bit Python from https://www.python.org/downloads/windows/
echo Include the Python launcher and Add Python to PATH, then reopen this folder.
pause
exit /b 1
:failed
echo.
echo Setup did not finish. Check your connection and the error above.
echo See README.md for troubleshooting. You can run setup.bat again.
pause
exit /b 1
