@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run setup.bat first and verify run.bat works.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m pip install "pyinstaller>=6.12,<7"
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onedir --windowed --name YouTubeLocalTranscriber --collect-all yt_dlp --collect-all yt_dlp_ejs --collect-all faster_whisper --collect-all ctranslate2 --collect-all onnxruntime --collect-all tokenizers --collect-all av --collect-all huggingface_hub main.py
if errorlevel 1 goto failed
echo.
echo Created dist\YouTubeLocalTranscriber\YouTubeLocalTranscriber.exe
echo Keep the entire dist\YouTubeLocalTranscriber folder together.
echo FFmpeg, Deno and model files are separate. See README.md.
pause
exit /b 0
:failed
echo Build failed. Read the messages above before trying again.
pause
exit /b 1
