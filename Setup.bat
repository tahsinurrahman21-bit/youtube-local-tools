@echo off
setlocal
title YouTube Local Tools setup
cd /d "%~dp0"
if not exist "%~dp0bootstrap\setup.ps1" (
    echo bootstrap\setup.ps1 is missing. Extract the WHOLE zip file first, then run Setup.bat again.
    pause
    exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap\setup.ps1" %*
set RESULT=%ERRORLEVEL%
echo.
if not "%RESULT%"=="0" (
    echo Setup did not finish. Read the messages above, and setup.log in the folder you chose.
    echo You can run Setup.bat again and choose the same folder to retry or repair.
) else (
    echo Setup finished. Open the apps from the folder that just opened.
)
pause
exit /b %RESULT%
