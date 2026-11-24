"""Local inference with process-isolated CUDA failure recovery."""
from __future__ import annotations

import logging
import multiprocessing as mp
import os
from pathlib import Path
import queue
import platform
import sys
import time

from storage import stop_process_tree
from utils import Cancelled, check_cancel

MODELS = ('tiny', 'base', 'small', 'medium', 'large-v3')


def choose_model(selection: str) -> str:
    if selection == 'auto':
        return 'small'  # multilingual and practical on CPU and modest GPUs
    if selection not in MODELS:
        raise ValueError('Please choose a supported Whisper model from the menu.')
    return selection


def resolve_model(selection: str, cache: Path, updates) -> str:
    from faster_whisper.utils import download_model
    from huggingface_hub.errors import LocalEntryNotFoundError
    model = choose_model(selection)
    root = cache / 'models'
    root.mkdir(parents=True, exist_ok=True)
    try:
        path = download_model(model, cache_dir=str(root), local_files_only=True)
        if all((Path(path) / name).is_file() for name in ('model.bin', 'config.json', 'tokenizer.json')):
            return path
    except LocalEntryNotFoundError:
        pass
    updates.put(('status', f'Downloading local {model} model (first use only). This may take several minutes…'))
    return download_model(model, cache_dir=str(root), local_files_only=False)


def inference_entry(media: str, cache: str, body: str, selection: str, language: str | None,
                    requested_device: str, cancel, updates):
    # Configure before importing model/network libraries. Once present, use only
    # local model files, including the tokenizer; no model-update checks are made.
    if os.name == 'nt':
        import ctypes
        ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x0002)
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    os.environ['HF_HUB_DISABLE_XET'] = '1'
    os.environ['HF_HOME'] = str(Path(cache) / 'models' / 'hub-state')
    os.environ['HF_HUB_DISABLE_PROGRESS_BARS'] = '1'
    os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'
    from settings import setup_logging
    setup_logging('local_transcriber', '-inference')
    try:
        if requested_device == 'mlx':
            from mac_inference import transcribe_apple
            result = transcribe_apple(media, cache, body, selection, language, cancel, updates)
            updates.put(('result', result))
            return
        if requested_device == 'cuda':
            from gpu_runtime import configure_cuda_libraries
            directories = configure_cuda_libraries()
            if directories:
                logging.info('Registered %s local NVIDIA runtime folders', len(directories))
        import ctranslate2
        from faster_whisper import WhisperModel
        from audio import audio_chunks, CHUNK_SECONDS, OVERLAP_SECONDS, SAMPLE_RATE
        from transcript import LANGUAGES, write_segment
        from utils import timestamp
        device = requested_device
        if device == 'cuda' and ctranslate2.get_cuda_device_count() < 1:
            updates.put(('status', 'CUDA unavailable. Device: CPU'))
            device = 'cpu'
        model_path = resolve_model(selection, Path(cache), updates)
        check_cancel(cancel)
        supported = ctranslate2.get_supported_compute_types(device)
        preferred = ('int8_float16', 'float16', 'float32') if device == 'cuda' else ('int8', 'float32')
        compute = next((kind for kind in preferred if kind in supported), 'default')
        label = f'NVIDIA GPU / CUDA ({compute})' if device == 'cuda' else f'CPU ({compute})'
        updates.put(('status', f'Loading {choose_model(selection)}. Device: {label}'))
        model = WhisperModel(model_path, device=device, compute_type=compute,
            local_files_only=True, cpu_threads=max(1, min(8, (os.cpu_count() or 2) - 1)))
        languages: set[str] = set()
        segment_count = 0
        last_time = 0.0
        chunks = audio_chunks(Path(media), cancel)
        try:
            with Path(body).open('w', encoding='utf-8', newline='\n') as handle:
                for offset, samples, is_last in chunks:
                    check_cancel(cancel)
                    updates.put(('status', f'Device: {label} • Detecting / transcribing at {timestamp(offset)}'))
                    segments, info = model.transcribe(samples, task='transcribe', language=language,
                        beam_size=5, vad_filter=True, condition_on_previous_text=False,
                        vad_parameters={'min_silence_duration_ms': 500})
                    chunk_has_speech = False
                    # Assign overlap segments by their midpoint, retaining complete
                    # words while avoiding most duplicates at minute boundaries.
                    left = offset + (OVERLAP_SECONDS / 2 if offset else 0)
                    right = offset + (len(samples) / SAMPLE_RATE if is_last else CHUNK_SECONDS - OVERLAP_SECONDS / 2)
                    for segment in segments:
                        check_cancel(cancel)
                        start, end = offset + segment.start, offset + segment.end
                        midpoint = (start + end) / 2
                        if midpoint < left or midpoint >= right or not segment.text.strip():
                            continue
                        write_segment(handle, max(start, last_time), segment.text)
                        last_time = max(start, last_time)
                        segment_count += 1
                        chunk_has_speech = True
                        updates.put(('position', end))
                    if chunk_has_speech:
                        languages.add(info.language)
                        updates.put(('status', f'Device: {label} • Language: {LANGUAGES.get(info.language, info.language)}'))
                    updates.put(('position', offset + len(samples) / SAMPLE_RATE))
                    handle.flush()
                if not segment_count:
                    handle.write('[No speech detected by the local model.]\n')
        finally:
            chunks.close()
        updates.put(('result', dict(device=label, model=choose_model(selection), languages=sorted(languages),
                                   forced_language=language, segments=segment_count)))
    except Cancelled:
        updates.put(('cancelled', True))
    except Exception as exc:
        logging.exception('Inference failed on %s', requested_device)
        updates.put(('error', str(exc)))


def run_attempt(media: Path, cache: Path, body: Path, selection: str, language: str | None,
                device: str, cancel, emit, duration: float | None) -> dict:
    context = mp.get_context('spawn')
    updates = context.Queue()
    process = context.Process(target=inference_entry,
        args=(str(media), str(cache), str(body), selection, language, device, cancel, updates))
    result, error = None, None
    cancelled_at = None
    process.start()

    def receive(kind, value):
        nonlocal result, error
        if kind == 'result':
            result = value
        elif kind == 'error':
            error = value
        elif kind == 'status':
            emit('stage', (value, 0.3))
            emit('log', value)
        elif kind == 'position':
            fraction = min(value / duration, 1) if duration and duration > 0 else 0
            emit('stage', (f'Transcribing… {fraction:.0%} (estimated)' if duration else
                            f'Transcribed through {value:.0f} seconds', 0.3 + 0.68 * fraction))

    try:
        while process.is_alive():
            if cancel.is_set():
                cancelled_at = cancelled_at or time.monotonic()
                if time.monotonic() - cancelled_at > 2:
                    stop_process_tree(process)
            try:
                receive(*updates.get(timeout=0.1))
            except queue.Empty:
                pass
        process.join()
        while True:
            try:
                receive(*updates.get_nowait())
            except queue.Empty:
                break
        check_cancel(cancel)
        if result is None or process.exitcode != 0:
            raise RuntimeError(error or f'The inference process stopped (exit code {process.exitcode}). '
                               'Check the inference log for missing CUDA / runtime libraries.')
        return result
    finally:
        if process.is_alive():
            stop_process_tree(process)
            process.join(timeout=3)
        updates.close()
        updates.join_thread()
        process.close()


def transcribe_media(media: Path, cache: Path, body: Path, selection: str, language: str | None,
                     cancel, emit, duration: float | None) -> dict:
    choose_model(selection)
    device = preferred_device()
    try:
        return run_attempt(media, cache, body, selection, language, device, cancel, emit, duration)
    except Cancelled:
        raise
    except Exception as gpu_error:
        if device == 'cpu':
            raise
        check_cancel(cancel)
        logging.exception('First inference attempt failed; retrying on CPU')
        emit('log', f'{device.upper()} unavailable: {gpu_error}. Retrying this video on CPU.')
        # The CPU child opens body with "w": incomplete GPU text cannot be duplicated.
        return run_attempt(media, cache, body, selection, language, 'cpu', cancel, emit, duration)


def preferred_device() -> str:
    if os.environ.get('YTTOOLS_GPU', 'auto') == 'cpu':
        return 'cpu'
    if sys.platform == 'darwin':
        return 'mlx' if platform.machine().lower() in ('arm64', 'aarch64') else 'cpu'
    return 'cuda'
