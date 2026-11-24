"""Apple silicon / Metal inference; imported only in the isolated GPU child."""
from pathlib import Path

from audio import audio_chunks, CHUNK_SECONDS, OVERLAP_SECONDS, SAMPLE_RATE
from transcript import LANGUAGES, write_segment
from utils import check_cancel, timestamp

# Immutable revisions avoid downloading a changed model behind the same name.
REVISIONS = {
    'tiny': '6caf9c55601caafbe6508a8b0d216bdf4783c4e8',
    'base': '1e3e249fb8d01c655324bd6841b1deadffd6d04c',
    'small': '45f3915923c7a79a5a5b5a7d909d39aeb0e5630e',
    'medium': '7fc08c4eac4c316526498f147dfdee6f6303f975',
    'large-v3': '49e6aa286ad60c14352c404340ded53710378a11',
}


def resolve_apple_model(selection, cache, updates):
    from huggingface_hub import snapshot_download
    from huggingface_hub.errors import LocalEntryNotFoundError
    from transcriber import choose_model
    model = choose_model(selection)
    kwargs = dict(repo_id=f'mlx-community/whisper-{model}-mlx', revision=REVISIONS[model],
                  cache_dir=str(Path(cache) / 'models' / 'apple'),
                  allow_patterns=['config.json', 'weights.npz'])
    try:
        path = snapshot_download(**kwargs, local_files_only=True)
        if all((Path(path) / name).is_file() for name in ('config.json', 'weights.npz')):
            return path
    except LocalEntryNotFoundError:
        pass
    updates.put(('status', f'Downloading Apple GPU {model} model (first use only)…'))
    return snapshot_download(**kwargs)


def transcribe_apple(media, cache, body, selection, language, cancel, updates):
    import mlx.core as mx
    import mlx_whisper
    from transcriber import choose_model
    if not mx.metal.is_available():
        raise RuntimeError('Apple Metal GPU is unavailable.')
    mx.set_default_device(mx.gpu)
    model_path = resolve_apple_model(selection, cache, updates)
    check_cancel(cancel)
    label = 'Apple GPU / Metal (float16)'
    updates.put(('status', f'Loading {choose_model(selection)}. Device: {label}'))
    languages, segment_count, last_time = set(), 0, 0.0
    chunks = audio_chunks(Path(media), cancel)
    try:
        with Path(body).open('w', encoding='utf-8', newline='\n') as handle:
            for offset, samples, is_last in chunks:
                check_cancel(cancel)
                updates.put(('status', f'Device: {label} • Transcribing at {timestamp(offset)}'))
                result = mlx_whisper.transcribe(samples, path_or_hf_repo=model_path,
                    task='transcribe', language=language, fp16=True, verbose=None,
                    condition_on_previous_text=False)
                left = offset + (OVERLAP_SECONDS / 2 if offset else 0)
                right = offset + (len(samples) / SAMPLE_RATE if is_last else CHUNK_SECONDS - OVERLAP_SECONDS / 2)
                chunk_has_speech = False
                for segment in result.get('segments', []):
                    check_cancel(cancel)
                    start, end = offset + segment['start'], offset + segment['end']
                    if not left <= (start + end) / 2 < right or not segment['text'].strip():
                        continue
                    write_segment(handle, max(start, last_time), segment['text'])
                    last_time = max(start, last_time)
                    segment_count += 1
                    chunk_has_speech = True
                    updates.put(('position', end))
                if chunk_has_speech:
                    detected = result.get('language') or language or 'unknown'
                    languages.add(detected)
                    updates.put(('status', f'Device: {label} • Language: {LANGUAGES.get(detected, detected)}'))
                updates.put(('position', offset + len(samples) / SAMPLE_RATE))
                handle.flush()
            if not segment_count:
                handle.write('[No speech detected by the local model.]\n')
    finally:
        chunks.close()
    return dict(device=label, model=choose_model(selection), languages=sorted(languages),
                forced_language=language, segments=segment_count)
