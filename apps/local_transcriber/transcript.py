from __future__ import annotations

from pathlib import Path
import shutil
from typing import TextIO

from utils import timestamp

LANGUAGES = {'en': 'English', 'bn': 'Bengali / Bangla', 'hi': 'Hindi'}
SEPARATOR = '=' * 64


def write_segment(handle: TextIO, start: float, text: str) -> None:
    clean = ' '.join(text.split())
    if clean:
        handle.write(f'[{timestamp(start, milliseconds=True)}] {clean}\n')


def append_success(handle: TextIO, number: int, metadata: dict, url: str, result: dict, body: Path) -> None:
    languages = ', '.join(LANGUAGES.get(code, code) for code in result['languages']) or 'No speech detected'
    qualifier = ' (user selected)' if result.get('forced_language') else ' (estimated per audio chunk)'
    title = ' '.join(str(metadata.get('title', 'Untitled')).split())
    handle.write(f'{SEPARATOR}\nVIDEO {number}\nTitle: {title}\nURL: {url}\n'
                 f'Detected language: {languages}{qualifier}\n'
                 f'Device: {result["device"]}\nModel: {result["model"]}\n'
                 f'{SEPARATOR}\n\n')
    with body.open('r', encoding='utf-8') as source:
        shutil.copyfileobj(source, handle, length=1024 * 1024)
    handle.write('\n\n')
    handle.flush()


def append_failure(handle: TextIO, number: int, url: str, reason: str) -> None:
    reason = ' '.join(str(reason).split())
    handle.write(f'{SEPARATOR}\nVIDEO {number}\nURL: {url}\nSTATUS: FAILED\nReason: {reason}\n{SEPARATOR}\n\n')
    handle.flush()
