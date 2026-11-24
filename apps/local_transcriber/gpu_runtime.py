"""Find optional NVIDIA DLLs without changing the user's system PATH."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import site
import sys
import uuid

from settings import config_folder

COMPONENTS = ('cuda_runtime', 'cuda_nvrtc', 'cublas', 'cudnn')
_directory_handles = []
_registered: set[str] = set()


def runtime_config() -> Path:
    return config_folder('local_transcriber') / 'gpu-runtime.json'


def load_runtime_root() -> Path | None:
    try:
        settings = json.loads(runtime_config().read_text(encoding='utf-8'))
        root = settings.get('package_root')
        if settings.get('version') == 1 and isinstance(root, str) and Path(root).is_absolute():
            return Path(root)
    except FileNotFoundError:
        return None
    except (OSError, ValueError, TypeError, AttributeError):
        logging.warning('GPU runtime configuration is missing or unreadable; checking other locations.')
    return None


def save_runtime_root(root: Path) -> None:
    destination = runtime_config()
    part = destination.with_suffix('.' + uuid.uuid4().hex + '.tmp')
    try:
        part.write_text(json.dumps({'version': 1, 'package_root': str(root.resolve())}, indent=2), encoding='utf-8')
        os.replace(part, destination)
    finally:
        part.unlink(missing_ok=True)


def find_dll_directories(roots: list[Path]) -> list[Path]:
    directories = []
    seen: set[str] = set()
    for root in roots:
        for component in COMPONENTS:
            directory = root / 'nvidia' / component / 'bin'
            key = str(directory.resolve()).casefold()
            if directory.is_dir() and key not in seen:
                directories.append(directory.resolve())
                seen.add(key)
    return directories


def configure_cuda_libraries(extra_root: Path | None = None) -> list[Path]:
    if os.name != 'nt':
        return []
    roots = [extra_root] if extra_root is not None else []
    saved = load_runtime_root()
    if saved is not None and saved not in roots:
        roots.append(saved)
    roots.extend(Path(folder) for folder in site.getsitepackages())
    if getattr(sys, 'frozen', False):
        roots.append(Path(sys.executable).parent / 'gpu-libraries')
        roots.append(Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent)))
    directories = find_dll_directories(roots)
    added = []
    for directory in directories:
        key = str(directory).casefold()
        if key in _registered:
            continue
        try:
            # Keep the handles alive; closing them removes the DLL search paths.
            _directory_handles.append(os.add_dll_directory(str(directory)))
            _registered.add(key)
            added.append(str(directory))
        except OSError:
            logging.exception('Could not register CUDA DLL folder %s', directory)
    if added:
        # Some NVIDIA/CTranslate2 DLLs use legacy LoadLibrary rather than the
        # newer search API. This PATH change affects only this worker process.
        os.environ['PATH'] = os.pathsep.join(added + [os.environ.get('PATH', '')])
    return directories


def validate_runtime_layout(root: Path) -> None:
    expected = {'cublas': 'cublas64_12.dll', 'cudnn': 'cudnn64_9.dll',
                'cuda_runtime': 'cudart64_12.dll'}
    missing = [name for component, name in expected.items()
               if not (root / 'nvidia' / component / 'bin' / name).is_file()]
    if missing:
        raise RuntimeError('GPU library installation is incomplete: ' + ', '.join(missing))
