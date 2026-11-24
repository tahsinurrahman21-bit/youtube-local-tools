from __future__ import annotations

import logging
from pathlib import Path
import time

from settings import setup_logging
from storage import create_workspace, publish, remove_workspace
from transcript import append_failure, append_success
from transcriber import transcribe_media
from utils import Cancelled, check_cancel
from youtube import obtain_media


def run_batch(settings: dict, videos, cancel, events, roots: dict):
    setup_logging('local_transcriber', '-worker')
    started = time.monotonic()
    results = []
    part = Path(roots['output']) / 'combined.txt'
    current = 0
    high_water = 0.0

    def emit(kind, value):
        nonlocal high_water
        if kind == 'stage':
            message, fraction = value
            high_water = max(high_water, current + fraction)
            events.put(('status', f'Video {current + 1} of {len(videos)}: {message}'))
            events.put(('progress', int(1000 * high_water / len(videos))))
        else:
            events.put((kind, value))

    try:
        with part.open('w', encoding='utf-8', newline='\n') as combined:
            for current, url in enumerate(videos):
                check_cancel(cancel)
                download_work = create_workspace(Path(roots['cache']))
                temp_work = create_workspace(Path(roots['temp']))
                checkpoint = combined.tell()
                try:
                    media, metadata = obtain_media(url, Path(settings['cache']), download_work,
                        settings['keep'], False, cancel, emit)
                    body = temp_work / 'transcript-body.txt'
                    result = transcribe_media(media, Path(settings['cache']), body, settings['model'],
                        settings['language'], cancel, emit, metadata.get('duration'))
                    check_cancel(cancel)
                    append_success(combined, current + 1, metadata, url.original, result, body)
                    results.append(dict(url=url.original, status='SUCCESS', **result))
                    emit('log', 'SUCCESS: ' + url.original)
                except Cancelled:
                    raise
                except Exception as exc:
                    logging.exception('Video failed: %s', url.original)
                    combined.seek(checkpoint)
                    combined.truncate()
                    append_failure(combined, current + 1, url.original, str(exc))
                    results.append(dict(url=url.original, status='FAILED', reason=str(exc)))
                    emit('log', f'FAILED: {url.original}: {exc}')
                finally:
                    remove_workspace(download_work)
                    remove_workspace(temp_work)
                events.put(('progress', int(1000 * (current + 1) / len(videos))))
        check_cancel(cancel)
        output = publish(part, Path(settings['output']), 'youtube_transcripts.txt')
        events.put(('done', dict(output=str(output), results=results,
                                elapsed=time.monotonic() - started, cancelled=False)))
    except Cancelled:
        events.put(('done', dict(output=None, results=results,
                                elapsed=time.monotonic() - started, cancelled=True)))
    except Exception as exc:
        logging.exception('Batch failed')
        events.put(('fatal', str(exc)))
    finally:
        part.unlink(missing_ok=True)
