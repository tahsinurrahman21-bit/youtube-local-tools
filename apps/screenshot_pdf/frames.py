from __future__ import annotations

import math
import re
from pathlib import Path
from dependencies import executable
from processes import run_process
from storage import space_warning
from utils import validate_interval


def ordered_frames(folder: Path) -> list[Path]:
    return sorted(folder.glob('frame_*.jpg'), key=lambda path: int(path.stem.split('_')[-1]))


def extract_frames(media: Path, folder: Path, interval: float, quality: int,
                   duration: float | None, cancel, emit) -> list[Path]:
    interval = validate_interval(interval)
    folder.mkdir(parents=True, exist_ok=True)
    estimate = math.ceil(duration / interval) if duration and duration > 0 else None
    if estimate:
        emit('log', f'Estimated screenshots: {estimate:,} (limited by source frame rate).')
        space_warning(folder, estimate * 500_000, emit)
    count = 0
    timestamps = []

    def progress(line: str):
        nonlocal count
        if 'showinfo' in line and 'pts_time:' in line:
            match = re.search(r'pts_time:([\d.eE+-]+)', line)
            if match:
                timestamps.append(float(match.group(1)))
        if line.startswith('frame='):
            count = int(line.partition('=')[2].split()[0])
            fraction = min(count / estimate, 1) if estimate else 0
            emit('stage', (f'Extracting screenshot {count}' + (f' / ~{estimate}' if estimate else ''),
                           0.25 + fraction * 0.5))

    # Crossings of the requested time grid avoid fps-filter midpoint sampling.
    # If T is below the source frame period, select every source frame once.
    selection = f"setpts=PTS-STARTPTS,select='isnan(prev_pts)+gt(floor(t/{interval:.12g}),floor(prev_t/{interval:.12g}))',showinfo"
    run_process([executable('ffmpeg'), '-hide_banner', '-nostdin', '-y', '-i', str(media),
        '-map', '0:v:0', '-an', '-sn', '-vf', selection, '-fps_mode', 'vfr',
        '-q:v', str(quality), '-progress', 'pipe:1', '-nostats', str(folder / 'frame_%09d.jpg')],
        cancel, progress)
    frames = ordered_frames(folder)
    if not frames:
        raise RuntimeError('No video frames were found.')
    if len(timestamps) != len(frames):
        raise RuntimeError('Could not match extracted frames to their timestamps.')
    (folder / 'timestamps.txt').write_text('\n'.join(str(t) for t in timestamps), encoding='utf-8')
    return frames
