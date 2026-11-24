from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
import time

from frames import extract_frames
from pdf_builder import StreamingPDF
from settings import setup_logging
from storage import create_workspace, publish, remove_workspace, space_warning
from utils import Cancelled, check_cancel, timestamp
from youtube import obtain_media


def run_batch(settings: dict, videos, cancel, events, roots: dict):
    # A QGuiApplication in this isolated process enables Unicode text shaping.
    if sys.platform != 'darwin':
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtGui import QGuiApplication
    qt_app = QGuiApplication.instance() or QGuiApplication([])
    setup_logging('screenshot_pdf', '-worker')
    started = time.monotonic()
    results, screenshots = [], 0
    output_work = Path(roots['output'])
    part = output_work / 'combined.pdf'
    pdf = None
    current = 0

    def emit(kind, value):
        if kind == 'stage':
            message, fraction = value
            events.put(('status', f'Video {current + 1} of {len(videos)}: {message}'))
            events.put(('progress', int(1000 * (current + fraction) / len(videos))))
        else:
            events.put((kind, value))

    try:
        pdf = StreamingPDF(part)
        for current, url in enumerate(videos):
            check_cancel(cancel)
            checkpoint = pdf.checkpoint()
            download_work = create_workspace(Path(roots['cache']))
            temp_work = create_workspace(Path(roots['temp']))
            try:
                media, metadata = obtain_media(url, Path(settings['cache']), download_work,
                    settings['keep'], True, cancel, emit)
                frames = extract_frames(media, temp_work / 'frames', float(settings['interval']),
                    int(settings['quality']), metadata.get('duration'), cancel, emit)
                space_warning(Path(settings['output']), sum(f.stat().st_size for f in frames), emit)
                check_cancel(cancel)
                pdf.title_page(current + 1, metadata, url.original)
                timestamps = (temp_work / 'frames' / 'timestamps.txt').read_text(encoding='utf-8').splitlines()
                for index, frame in enumerate(frames):
                    check_cancel(cancel)
                    stamp = timestamp(float(timestamps[index]), milliseconds=True)
                    caption = f'{metadata["title"]} | Timestamp: {stamp}' if settings['captions'] else ''
                    pdf.add_page(frame, caption)
                    if index % 10 == 0 or index == len(frames) - 1:
                        emit('stage', (f'Creating PDF: screenshot {index + 1}/{len(frames)}',
                                       0.75 + 0.24 * (index + 1) / len(frames)))
                screenshots += len(frames)
                results.append(dict(url=url.original, status='SUCCESS', screenshots=len(frames)))
                emit('log', f'SUCCESS: {url.original} ({len(frames)} screenshots)')
            except Cancelled:
                pdf.rollback(checkpoint)
                raise
            except Exception as exc:
                logging.exception('Video failed: %s', url.original)
                pdf.rollback(checkpoint)
                pdf.error_page(current + 1, url.original, str(exc))
                results.append(dict(url=url.original, status='FAILED', reason=str(exc)))
                emit('log', f'FAILED: {url.original}: {exc}')
            finally:
                remove_workspace(download_work)
                remove_workspace(temp_work)
            events.put(('progress', int(1000 * (current + 1) / len(videos))))
        check_cancel(cancel)
        pdf.finish()
        pdf.close()
        pdf = None
        result_path = publish(part, Path(settings['output']), 'youtube_screenshots.pdf')
        events.put(('done', dict(output=str(result_path), results=results, screenshots=screenshots,
                                elapsed=time.monotonic() - started, cancelled=False)))
    except Cancelled:
        events.put(('done', dict(output=None, results=results, screenshots=screenshots,
                                elapsed=time.monotonic() - started, cancelled=True)))
    except Exception as exc:
        logging.exception('Batch failed')
        events.put(('fatal', str(exc)))
    finally:
        if pdf:
            pdf.close()
        part.unlink(missing_ok=True)
