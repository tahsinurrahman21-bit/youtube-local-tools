"""Build the small Windows setup zip that is attached to a GitHub Release.

Usage (any Python 3.9+, standard library only):

    python scripts/build_release.py            # version read from bootstrap/install.py
    python scripts/build_release.py --version 1.1.0

Output: dist/YouTubeLocalTools-<version>-Windows-Setup.zip  (+ .sha256)

The zip contains only project source and the setup scripts. It deliberately does
NOT contain Python, uv, FFmpeg, Deno, NVIDIA libraries or Whisper models: Setup
downloads those from their official distributors, with checksums where available,
so their licenses are respected and the download stays small.
"""
from __future__ import annotations

import argparse
import hashlib
import io
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {'__pycache__', '.venv', '.pytest_cache', 'build', 'dist', 'tools'}
BOOTSTRAP_FILES = ('setup.ps1', 'install.py', 'launch.py', 'assets.json', 'THIRD-PARTY-NOTICES.txt')
TOP_FILES = ('Setup.bat', 'README.md', 'LICENSE', 'THIRD-PARTY-NOTICES.txt')
CRLF_SUFFIXES = {'.bat', '.cmd', '.ps1'}


def detect_version() -> str:
    text = (ROOT / 'bootstrap' / 'install.py').read_text(encoding='utf-8')
    match = re.search(r"version='([0-9.]+)'", text)
    return match.group(1) if match else '0.0'


def source_files(folder: Path):
    for path in sorted(folder.rglob('*')):
        if path.is_file() and not SKIP_DIRS.intersection(path.relative_to(folder).parts) and path.suffix != '.pyc':
            yield path


def read_for_zip(path: Path) -> bytes:
    data = path.read_bytes()
    if path.suffix.lower() in CRLF_SUFFIXES:
        data = data.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
    return data


def build_apps_zip() -> bytes:
    apps = ROOT / 'apps'
    if not (apps / 'local_transcriber' / 'main.py').is_file():
        raise SystemExit('apps/ source folder not found.')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as package:
        for path in source_files(apps):
            package.writestr(path.relative_to(apps).as_posix(), read_for_zip(path))
    return buffer.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--version')
    args = parser.parse_args()
    version = args.version or detect_version()
    name = f'YouTubeLocalTools-{version}-Windows-Setup'
    out_dir = ROOT / 'dist'
    out_dir.mkdir(exist_ok=True)
    target = out_dir / f'{name}.zip'
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as release:
        for file in TOP_FILES:
            release.writestr(f'{name}/{file}', read_for_zip(ROOT / file))
        for file in BOOTSTRAP_FILES:
            release.writestr(f'{name}/bootstrap/{file}', read_for_zip(ROOT / 'bootstrap' / file))
        release.writestr(f'{name}/bootstrap/apps.zip', build_apps_zip())
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    (out_dir / f'{name}.zip.sha256').write_text(f'{digest}  {target.name}\n', encoding='utf-8')
    print(f'Built {target} ({target.stat().st_size / 1024:.0f} KB)')
    print(f'SHA-256 {digest}')


if __name__ == '__main__':
    main()
