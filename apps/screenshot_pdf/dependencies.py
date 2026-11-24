from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import sys


def executable(name: str) -> str | None:
    override = os.environ.get('YTTOOLS_' + name.upper())
    if override and Path(override).is_file():
        return override
    root = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
    for candidate in (root / 'tools' / f'{name}.exe', root / 'tools' / name):
        if candidate.is_file():
            return str(candidate)
    return shutil.which(name)


def check_dependencies(transcriber: bool = False) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    packages = [('yt_dlp', 'yt-dlp'), ('yt_dlp_ejs', 'yt-dlp[default]'), ('psutil', 'psutil')]
    packages += [('faster_whisper', 'faster-whisper')] if transcriber else [('PIL', 'Pillow')]
    for module, package in packages:
        if importlib.util.find_spec(module) is None:
            errors.append(f'{package} is missing. Close the app and run setup.bat.')
    if not executable('ffmpeg'):
        errors.append('FFmpeg was not found. Install it and add its bin folder to PATH, '
                      'or put ffmpeg.exe in this app\'s tools folder. See README.md.')
    if not executable('deno') and not executable('node'):
        warnings.append('Deno (recommended) or Node.js is missing. Current YouTube downloads '
                        'need a JavaScript runtime; see README.md. Cached videos still work.')
    return errors, warnings
