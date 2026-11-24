"""Install NVIDIA's runtime wheels on a user-selected drive."""
from __future__ import annotations

import argparse
import ctypes
import logging
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import uuid

from gpu_runtime import configure_cuda_libraries, save_runtime_root, validate_runtime_layout
from settings import setup_logging

MIN_FREE_GB = 6


def install_gpu_runtime(root: Path) -> Path:
    if os.name != 'nt' or platform.machine().lower() not in ('amd64', 'x86_64'):
        raise RuntimeError('This installer is for 64-bit Windows on an Intel/AMD PC.')
    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    free_gb = shutil.disk_usage(root).free / 1024**3
    if free_gb < MIN_FREE_GB:
        raise RuntimeError(f'This drive has only {free_gb:.1f} GB free. Choose a drive with at least '
                           f'{MIN_FREE_GB} GB free for the download, installation and spare space.')
    destination = root / ('cuda12-cudnn9-' + uuid.uuid4().hex[:8])
    requirements = Path(__file__).with_name('requirements-gpu.txt')
    print(f'Installing official NVIDIA runtime packages to {destination}', flush=True)
    print('The download is approximately 1.3 GB. Leave this window open.', flush=True)
    # Both the downloaded wheels and pip's extraction files stay on this drive.
    with tempfile.TemporaryDirectory(prefix='.gpu-setup-', dir=root) as staging:
        environment = dict(os.environ, TEMP=staging, TMP=staging, TMPDIR=staging, PYTHONUTF8='1')
        packages = Path(staging) / 'packages'
        command = [sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check',
                   '--no-cache-dir', '--only-binary=:all:', '--target', str(packages),
                   '-r', str(requirements)]
        subprocess.run(command, env=environment, check=True)
        validate_runtime_layout(packages)
        packages.rename(destination)
    return destination


def verify_dll_loading(root: Path) -> None:
    directories = configure_cuda_libraries(root)
    for name in ('cudart64_12.dll', 'cublasLt64_12.dll', 'cublas64_12.dll', 'cudnn64_9.dll'):
        path = next((folder / name for folder in directories if (folder / name).is_file()), None)
        if path is None:
            raise RuntimeError(f'Missing GPU library: {name}')
        ctypes.WinDLL(str(path))
    import ctranslate2
    count = ctranslate2.get_cuda_device_count()
    if count < 1:
        raise RuntimeError('Libraries are installed, but no compatible NVIDIA CUDA device was detected.')
    print(f'NVIDIA DLL loading succeeded; {count} CUDA device(s) detected.', flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, help='Folder on a drive with at least 6 GB free')
    parser.add_argument('--verify-only', type=Path, help='Check an existing NVIDIA package folder')
    args = parser.parse_args()
    setup_logging('local_transcriber', '-gpu-setup')
    try:
        if args.verify_only:
            verify_dll_loading(args.verify_only)
            return 0
        directory = args.directory
        if directory is None:
            from PySide6.QtWidgets import QApplication, QFileDialog
            app = QApplication.instance() or QApplication([])
            selected = QFileDialog.getExistingDirectory(None, 'Choose where to store NVIDIA libraries (6 GB free required)')
            if not selected:
                print('GPU setup cancelled. Existing settings are unchanged.')
                return 0
            directory = Path(selected) / 'YouTubeLocalTools-GPU'
        installed = install_gpu_runtime(directory)
        # Verify in a fresh process, as NVIDIA libraries may already have been
        # loaded from an older location in an interactive installer session.
        subprocess.run([sys.executable, str(Path(__file__).resolve()), '--verify-only', str(installed)], check=True)
        # Preserve the previous setting unless the new libraries can be loaded.
        save_runtime_root(installed)
        print('\nGPU libraries are ready. Close and reopen run.bat, then test a short video.', flush=True)
        print('A completed transcript must show Device: NVIDIA GPU / CUDA to confirm actual GPU inference.', flush=True)
        return 0
    except Exception as exc:
        logging.exception('GPU setup failed')
        print(f'\nGPU setup did not finish: {exc}\nSee app-gpu-setup.log in the settings folder.', flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
