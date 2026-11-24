"""yt-dlp API downloads and cross-application, opt-in media reuse."""
from __future__ import annotations

import json
import logging
from pathlib import Path
import shutil
import time
import uuid

from dependencies import executable
from storage import space_warning
from utils import VideoURL, check_cancel, safe_filename


class DownloadLog:
    def __init__(self, emit):
        self.emit = emit

    def debug(self, message):
        logging.getLogger('yt_dlp').debug(message)

    def warning(self, message):
        logging.warning('%s', message)
        self.emit('log', 'YouTube: ' + message)

    def error(self, message):
        logging.error('%s', message)


def cached_media(cache: Path, video_id: str, video_required: bool):
    modes = ('video',) if video_required else ('video', 'audio')
    for mode in modes:
        index = cache / 'media' / f'{video_id}-{mode}.json'
        try:
            info = json.loads(index.read_text(encoding='utf-8'))
            name = info['filename']
            if Path(name).name != name:
                continue
            media = index.parent / name
            if media.is_file() and media.stat().st_size == info['size'] and info['size'] > 0:
                return media, info
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return None


def obtain_media(url: VideoURL, cache: Path, work: Path, keep: bool,
                 video_required: bool, cancel, emit) -> tuple[Path, dict]:
    check_cancel(cancel)
    cached = cached_media(cache, url.video_id, video_required)
    if cached:
        emit('log', 'Using saved media: ' + str(cached[0]))
        return cached
    from yt_dlp import YoutubeDL
    # Keeping a download means retaining a useful <=1080p video with audio in either app.
    want_video = video_required or keep
    last_update = 0.0

    def hook(data):
        nonlocal last_update
        check_cancel(cancel)
        if time.monotonic() - last_update < 0.25 and data.get('status') != 'finished':
            return
        last_update = time.monotonic()
        total = data.get('total_bytes') or data.get('total_bytes_estimate') or 0
        fraction = data.get('downloaded_bytes', 0) / total if total else 0
        emit('stage', ('Downloading media', min(1.0, fraction) * 0.25))

    deno, node = executable('deno'), executable('node')
    runtimes = {'deno': {'path': deno}} if deno else ({'node': {'path': node}} if node else {})
    options = {
        'noplaylist': True, 'quiet': True, 'no_warnings': False,
        'logger': DownloadLog(emit), 'progress_hooks': [hook],
        'socket_timeout': 20, 'retries': 2, 'fragment_retries': 2,
        'concurrent_fragment_downloads': 1, 'cachedir': str(cache / 'yt-dlp'),
        'paths': {'home': str(work), 'temp': str(work)},
        'outtmpl': 'source.%(ext)s',
        'windowsfilenames': True, 'ffmpeg_location': executable('ffmpeg'),
        'js_runtimes': runtimes, 'remote_components': set(),
        'format': ('bv[height<=1080]+ba/b[height<=1080]' if want_video else 'ba/b'),
        'merge_output_format': 'mkv',
    }
    emit('stage', ('Reading video information', 0.01))
    with YoutubeDL(options) as downloader:
        info = downloader.extract_info(url.canonical, download=False)
        check_cancel(cancel)
        if not info or info.get('_type') in ('playlist', 'multi_video'):
            raise ValueError('Please supply an individual YouTube video URL, not a playlist.')
        if info.get('is_live') or info.get('live_status') == 'is_upcoming':
            raise ValueError('Live and upcoming streams are unsupported. Use a finished video.')
        estimated = info.get('filesize') or info.get('filesize_approx') or 0
        if not estimated:
            estimated = sum(f.get('filesize') or f.get('filesize_approx') or 0
                            for f in info.get('requested_formats', []))
        space_warning(work, int(estimated * 2), emit)
        emit('log', f"Title: {info.get('title', url.video_id)}; duration: {info.get('duration', 'unknown')} seconds")
        info = downloader.process_ie_result(info, download=True)
    check_cancel(cancel)
    candidates = [path for path in work.glob('source.*')
                  if path.suffix.lower() in ('.mp4', '.mkv', '.webm', '.m4a', '.mp3', '.ogg', '.opus', '.flac', '.wav')]
    merged = work / 'source.mkv'
    media = merged if merged in candidates else (max(candidates, key=lambda p: p.stat().st_size) if candidates else None)
    if media is None:
        raise RuntimeError('Download finished but no usable media file was produced.')
    metadata = dict(title=info.get('title', url.video_id), duration=info.get('duration'),
                    video_id=url.video_id, url=url.original)
    if keep:
        saved = cache / 'media'
        saved.mkdir(parents=True, exist_ok=True)
        name = f'{safe_filename(metadata["title"], 70)} [{url.video_id}] {uuid.uuid4().hex[:8]}{media.suffix}'
        destination = saved / name
        # work and cache/media share a volume. Rename avoids a second large copy.
        media.rename(destination)
        metadata.update(filename=name, size=destination.stat().st_size)
        mode = 'video' if want_video else 'audio'
        index = saved / f'{url.video_id}-{mode}.json'
        part = saved / (index.name + '.' + uuid.uuid4().hex + '.tmp')
        part.write_text(json.dumps(metadata, ensure_ascii=False), encoding='utf-8')
        part.replace(index)
        emit('log', 'Kept reusable video: ' + str(destination))
        return destination, metadata
    return media, metadata
