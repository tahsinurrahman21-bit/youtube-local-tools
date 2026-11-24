"""Local preferences and rolling logs; no network services."""
from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
import os
import sys
from pathlib import Path


def config_folder(app: str) -> Path:
    if os.environ.get('YTTOOLS_CONFIG_ROOT'):
        folder = Path(os.environ['YTTOOLS_CONFIG_ROOT']) / app
    else:
        fallback = Path.home() / ('Library/Application Support' if sys.platform == 'darwin' else '.local/share')
        base = Path(os.environ.get('LOCALAPPDATA', str(fallback)))
        folder = base / 'YouTubeLocalTools' / app
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def defaults() -> dict:
    from PySide6.QtCore import QStandardPaths
    documents = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
    root = Path(os.environ['YTTOOLS_DATA_ROOT']) if os.environ.get('YTTOOLS_DATA_ROOT') else (
        Path(documents or str(Path.home() / 'Documents')) / 'YouTubeLocalTools')
    return dict(cache=str(root / 'Downloads'), temp=str(root / 'Temp'), output=str(root / 'Output'),
                keep=False, interval='10', quality=2, captions=True, language=None, model='auto')


def load_settings(app: str) -> dict:
    result = defaults()
    try:
        saved = json.loads((config_folder(app) / 'settings.json').read_text(encoding='utf-8'))
        if isinstance(saved, dict):
            result.update({key: value for key, value in saved.items() if key in result})
    except (OSError, ValueError):
        pass
    return result


def save_settings(app: str, settings: dict) -> None:
    import uuid
    destination = config_folder(app) / 'settings.json'
    part = destination.with_suffix('.' + uuid.uuid4().hex + '.tmp')
    try:
        part.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(part, destination)
    finally:
        part.unlink(missing_ok=True)


def setup_logging(app: str, suffix: str = '') -> Path:
    path = config_folder(app) / f'app{suffix}.log'
    handler = RotatingFileHandler(path, maxBytes=3_000_000, backupCount=2, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
    logging.getLogger().setLevel(logging.INFO)
    logging.getLogger().addHandler(handler)
    return path
