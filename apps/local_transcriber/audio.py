"""Decode audio incrementally. Each Whisper input is at most one minute long."""
from __future__ import annotations

from collections import deque
from pathlib import Path
import subprocess
import threading

import numpy as np

from dependencies import executable
from utils import check_cancel

SAMPLE_RATE = 16_000
CHUNK_SECONDS = 60
OVERLAP_SECONDS = 2


def audio_chunks(media: Path, cancel):
    process = subprocess.Popen([executable('ffmpeg'), '-hide_banner', '-loglevel', 'error',
        '-nostdin', '-i', str(media), '-map', '0:a:0', '-vn', '-sn', '-ac', '1', '-ar',
        str(SAMPLE_RATE), '-f', 's16le', 'pipe:1'], stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    errors = deque(maxlen=25)

    def read_errors():
        for line in process.stderr:
            errors.append(line.decode('utf-8', errors='replace').strip())

    reader = threading.Thread(target=read_errors, daemon=True)
    reader.start()
    chunk_bytes = CHUNK_SECONDS * SAMPLE_RATE * 2
    overlap_bytes = OVERLAP_SECONDS * SAMPLE_RATE * 2
    offset = 0.0
    previous = b''
    carried_new_bytes = 0
    try:
        while True:
            check_cancel(cancel)
            buffer = bytearray(previous)
            new_bytes = carried_new_bytes
            while len(buffer) < chunk_bytes:
                check_cancel(cancel)
                piece = process.stdout.read(min(65536, chunk_bytes - len(buffer)))
                if not piece:
                    break
                buffer.extend(piece)
                new_bytes += len(piece)
            if new_bytes == 0:
                break
            lookahead = process.stdout.read(2) if len(buffer) == chunk_bytes else b''
            is_last = not lookahead
            audio = np.frombuffer(buffer, dtype='<i2').astype(np.float32) / 32768.0
            previous = bytes(buffer[-overlap_bytes:]) + lookahead
            carried_new_bytes = len(lookahead)
            yield offset, audio, is_last
            offset += CHUNK_SECONDS - OVERLAP_SECONDS
            if is_last:
                break
        if process.wait() != 0:
            reader.join(timeout=1)
            raise RuntimeError('Could not decode audio: ' + '\n'.join(errors))
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        reader.join(timeout=2)
        process.stdout.close()
        process.stderr.close()
