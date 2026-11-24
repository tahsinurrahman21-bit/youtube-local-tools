"""Only delete marked, app-owned work directories. Never delete cache entries."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import shutil
import tempfile
import uuid

import psutil

MARKER = '.youtube-local-tools-owner.json'
PREFIX = '.ytt-work-'


def prepare_folders(settings: dict) -> list[str]:
    warnings = []
    for name in ('cache', 'temp', 'output'):
        if not str(settings.get(name, '')).strip():
            raise ValueError(f'Choose a {name} folder.')
        folder = Path(settings[name]).expanduser().resolve()
        folder.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=folder) as test:
            test.write(b'writable')
            test.flush()
        settings[name] = str(folder)
        free = shutil.disk_usage(folder).free
        if free < 2 * 1024**3:
            warnings.append(f'{name.title()}: only {free / 1024**3:.2f} GB free at {folder}. '
                            'Long videos, small intervals, and large models can need much more.')
    return warnings


def create_workspace(root: Path) -> Path:
    folder = root / (PREFIX + uuid.uuid4().hex)
    folder.mkdir()
    process = psutil.Process()
    (folder / MARKER).write_text(json.dumps({'owner': 'youtube-local-tools-v1',
        'pid': process.pid, 'created': process.create_time(), 'name': folder.name}), encoding='utf-8')
    return folder


def remove_workspace(folder: Path) -> None:
    try:
        if folder.is_symlink() or not folder.name.startswith(PREFIX):
            return
        data = json.loads((folder / MARKER).read_text(encoding='utf-8'))
        if data.get('owner') != 'youtube-local-tools-v1' or data.get('name') != folder.name:
            return
        shutil.rmtree(folder)
    except (OSError, ValueError):
        logging.exception('Could not clean work folder %s', folder)


def clean_stale(root: Path) -> None:
    for folder in root.glob(PREFIX + '*'):
        try:
            data = json.loads((folder / MARKER).read_text(encoding='utf-8'))
            if data.get('owner') != 'youtube-local-tools-v1':
                continue
            try:
                process = psutil.Process(int(data['pid']))
                if abs(process.create_time() - float(data['created'])) < 1:
                    continue
            except psutil.NoSuchProcess:
                pass
            remove_workspace(folder)
        except (OSError, ValueError, KeyError, psutil.Error):
            logging.warning('Skipping unverified work folder %s', folder)


def publish(part: Path, output: Path, filename: str) -> Path:
    """Reserve a unique destination so existing results are never overwritten."""
    base = Path(filename)
    for index in range(1, 100_000):
        candidate = output / (base.name if index == 1 else f'{base.stem}_{index}{base.suffix}')
        try:
            with candidate.open('xb'):
                pass
        except FileExistsError:
            continue
        try:
            # part is already on the output volume, so this rename is atomic.
            os.replace(part, candidate)
            return candidate
        except BaseException:
            candidate.unlink(missing_ok=True)
            raise
    raise OSError('Too many files with the same output name.')


def space_warning(root: Path, estimate: int, emit) -> None:
    free = shutil.disk_usage(root).free
    if estimate > free:
        emit('log', f'WARNING: estimated space needed {estimate / 1024**3:.2f} GB; '
             f'available {free / 1024**3:.2f} GB at {root}. Cancel or free space if necessary.')


def stop_process_tree(process) -> None:
    try:
        parent = psutil.Process(process.pid)
        children = parent.children(recursive=True)
        for child in reversed(children):
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        parent.kill()
        psutil.wait_procs(children + [parent], timeout=3)
    except psutil.NoSuchProcess:
        pass
