"""Cancellable, shell-free subprocess execution with bounded output buffering."""
from __future__ import annotations

from collections import deque
import queue
import subprocess
import threading
from utils import check_cancel


def run_process(args: list[str], cancel, on_line=None) -> str:
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL, text=True, encoding='utf-8', errors='replace',
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    lines: queue.Queue = queue.Queue(maxsize=256)
    finished = threading.Event()

    def read_output():
        try:
            for line in process.stdout:
                while not finished.is_set():
                    try:
                        lines.put(line.rstrip(), timeout=0.1)
                        break
                    except queue.Full:
                        pass
        finally:
            finished.set()

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    tail = deque(maxlen=50)
    try:
        while not finished.is_set() or not lines.empty():
            check_cancel(cancel)
            try:
                line = lines.get(timeout=0.1)
            except queue.Empty:
                continue
            tail.append(line)
            if on_line:
                on_line(line)
        check_cancel(cancel)
        if process.wait() != 0:
            raise RuntimeError('FFmpeg could not process this media. ' + '\n'.join(tail)[-2500:])
        return '\n'.join(tail)
    finally:
        finished.set()
        if process.poll() is None:
            process.kill()
        process.wait()
        reader.join(timeout=2)
        process.stdout.close()
