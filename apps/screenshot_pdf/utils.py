"""Small, dependency-light validation helpers."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse


@dataclass(frozen=True)
class VideoURL:
    original: str
    canonical: str
    video_id: str


def parse_urls(text: str) -> tuple[list[VideoURL], list[str], list[str]]:
    videos, duplicates, invalid = [], [], []
    seen: set[str] = set()
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            parsed = urlparse(raw if '://' in raw else 'https://' + raw)
            host = (parsed.hostname or '').lower()
            if parsed.scheme not in ('https', 'http') or parsed.username or parsed.password:
                raise ValueError()
            parts = parsed.path.strip('/').split('/')
            video_id = ''
            if host in ('youtu.be', 'www.youtu.be') and len(parts) == 1:
                video_id = parts[0]
            elif host in ('youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com'):
                if parsed.path.rstrip('/') == '/watch':
                    video_id = parse_qs(parsed.query).get('v', [''])[0]
                elif len(parts) == 2 and parts[0] in ('shorts', 'embed', 'live'):
                    video_id = parts[1]
            if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
                raise ValueError()
            if video_id in seen:
                duplicates.append(raw)
            else:
                seen.add(video_id)
                videos.append(VideoURL(raw, f'https://www.youtube.com/watch?v={video_id}', video_id))
        except (ValueError, TypeError):
            invalid.append(raw)
    return videos, duplicates, invalid


def safe_filename(value: str, limit: int = 100) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', value).strip(' .')[:limit].rstrip(' .')
    if not value:
        value = 'untitled'
    if re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])', value.split('.')[0], re.I):
        value = '_' + value
    return value


def timestamp(seconds: float, milliseconds: bool = False) -> str:
    ticks = max(0, round(seconds * 1000)) if math.isfinite(seconds) else 0
    whole, ms = divmod(ticks, 1000)
    hours, rest = divmod(whole, 3600)
    minutes, sec = divmod(rest, 60)
    return f'{hours:02}:{minutes:02}:{sec:02}' + (f'.{ms:03}' if milliseconds else '')


def validate_interval(value: str | float) -> float:
    interval = float(value)
    if not math.isfinite(interval) or interval <= 0:
        raise ValueError('Screenshot interval must be a finite number greater than 0.')
    return interval


class Cancelled(Exception):
    pass


def check_cancel(event) -> None:
    if event.is_set():
        raise Cancelled('Cancelled by the user.')
