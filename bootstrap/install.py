"""Shared installer worker. Invoked by the platform setup after private Python bootstrap."""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import plistlib
import shlex
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile

APPS = {'screenshot_pdf': 'YouTube Screenshots to PDF', 'local_transcriber': 'YouTube Local Transcriber'}
BASE = ['PySide6==6.11.2', 'yt-dlp[default]==2026.8.19', 'Pillow==12.3.0',
        'faster-whisper==1.2.1', 'ctranslate2==4.8.2', 'psutil==7.2.2', 'imageio-ffmpeg==0.6.0']
CUDA = ['nvidia-cublas-cu12==12.9.2.10', 'nvidia-cudnn-cu12==9.26.0.51',
        'nvidia-cuda-runtime-cu12==12.9.79', 'nvidia-cuda-nvrtc-cu12==12.9.86']
APPLE = ['mlx-whisper==0.4.3', 'mlx==0.32.3']

def log(text):
    print(text, flush=True)

def run(args, **kw):
    log('Preparing ' + Path(str(args[0])).name + ' components…')
    subprocess.run([str(x) for x in args], check=True, **kw)

def private_environment(root):
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(('UV_', 'PIP_', 'PYTHON')) or key in ('VIRTUAL_ENV', 'CONDA_PREFIX'):
            env.pop(key, None)
    env.update(UV_PYTHON_INSTALL_DIR=str(root/'runtime'/'python'), UV_CACHE_DIR=str(root/'setup-cache'),
               UV_PYTHON_INSTALL_BIN='false', UV_PYTHON_INSTALL_REGISTRY='false', UV_NO_CONFIG='true',
               UV_NO_PROGRESS='true', UV_LINK_MODE='copy', PYTHONUTF8='1', PYTHONNOUSERSITE='1',
               TMP=str(root/'setup-temp'), TEMP=str(root/'setup-temp'), TMPDIR=str(root/'setup-temp'),
               YTTOOLS_CONFIG_ROOT=str(root/'settings'), YTTOOLS_DATA_ROOT=str(root/'data'))
    return env

def fetch(asset, destination):
    if not asset.get('sha256') or len(asset['sha256']) != 64:
        raise RuntimeError('Missing download checksum.')
    part = destination.with_suffix('.part')
    request = urllib.request.Request(asset['url'], headers={'User-Agent':'YouTubeLocalTools-Setup/1.1'})
    digest = hashlib.sha256()
    with urllib.request.urlopen(request, timeout=90) as response, part.open('wb') as output:
        while block := response.read(1024 * 1024):
            digest.update(block)
            output.write(block)
    if digest.hexdigest() != asset['sha256']:
        part.unlink(missing_ok=True)
        raise RuntimeError('Download checksum did not match: ' + destination.name)
    os.replace(part, destination)

def extract_payload(archive, root):
    apps = root/'apps'
    apps.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as package:
        for entry in package.infolist():
            target = (apps/entry.filename).resolve()
            if not target.is_relative_to(apps.resolve()):
                raise ValueError('Invalid package path.')
            if not entry.is_dir():
                target.parent.mkdir(parents=True, exist_ok=True)
                with package.open(entry) as source, target.open('wb') as dest:
                    shutil.copyfileobj(source, dest)

def has_nvidia():
    import ctypes
    try:
        driver = ctypes.WinDLL('nvcuda.dll')
        if driver.cuInit(0) != 0:
            return False
        count = ctypes.c_int()
        return driver.cuDeviceGetCount(ctypes.byref(count)) == 0 and count.value > 0
    except (OSError, AttributeError):
        return False

def mac_bundle(root, app, title):
    bundle = root/(title+'.app')
    contents = bundle/'Contents'
    executable = contents/'MacOS'/'launch'
    executable.parent.mkdir(parents=True, exist_ok=True)
    # Compute paths from bundle location, so spaces and Unicode need no interpolation.
    executable.write_text('#!/bin/bash\nset -e\nROOT="$(cd "$(dirname "$0")/../../.." && pwd)"\n'
        'exec "$ROOT/runtime/env/bin/python" "$ROOT/launch.py" '+shlex.quote(app)+'\n', encoding='utf-8')
    executable.chmod(0o755)
    with (contents/'Info.plist').open('wb') as handle:
        plistlib.dump(dict(CFBundleName=title, CFBundleDisplayName=title, CFBundleExecutable='launch',
            CFBundleIdentifier='local.youtubetools.'+app.replace('_',''), CFBundlePackageType='APPL',
            CFBundleVersion='1.1', CFBundleShortVersionString='1.1', LSMinimumSystemVersion='14.0',
            NSHighResolutionCapable=True), handle)

def install(root, assets_dir, gpu):
    root = root.resolve()
    marker = root/'.youtube-local-tools-install'
    if not marker.is_file():
        raise RuntimeError('The setup ownership marker is missing. Run the platform setup first.')
    env = private_environment(root)
    os.environ.update(env)
    os.environ['YTTOOLS_GPU'] = 'auto' if gpu else 'cpu'
    uv = root/'bootstrap'/('uv.exe' if os.name == 'nt' else 'uv')
    py = root/'runtime'/'env'/('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    for directory in ('setup-temp','setup-cache','settings','data','tools'):
        (root/directory).mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(root).free < (8 if gpu else 3) * 1024**3:
        raise RuntimeError('Please free at least ' + ('8 GB' if gpu else '3 GB') + ' on the selected drive and run setup again.')
    log('Installing the two apps and required libraries…')
    run([uv,'pip','install','--python',py,'--only-binary',':all:',*BASE], env=env)
    extract_payload(assets_dir/'apps.zip', root)
    shutil.copy2(assets_dir/'launch.py', root/'launch.py')
    # Qt ships redistributable MSVC libraries. Register their app-local folder
    # on interpreter startup so CTranslate2 also works without a global VC install.
    if os.name == 'nt':
        site = root/'runtime'/'env'/'Lib'/'site-packages'
        (site/'sitecustomize.py').write_text(
            "import os, pathlib\n_folder = pathlib.Path(__file__).parent / 'PySide6'\n"
            "if _folder.is_dir():\n    _dll_handle = os.add_dll_directory(str(_folder))\n"
            "    os.environ['PATH'] = str(_folder) + os.pathsep + os.environ.get('PATH', '')\n", encoding='utf-8')
    log('Installing FFmpeg and the YouTube JavaScript runtime…')
    result = subprocess.check_output([str(py),'-c','import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())'], env=env, text=True).strip()
    shutil.copy2(result, root/'tools'/('ffmpeg.exe' if os.name == 'nt' else 'ffmpeg'))
    if os.name != 'nt':
        (root/'tools'/'ffmpeg').chmod(0o755)
    arch = 'aarch64' if platform.machine().lower() in ('arm64','aarch64') else 'x86_64'
    triple = 'x86_64-pc-windows-msvc' if os.name == 'nt' else arch+'-apple-darwin'
    manifest = json.loads((assets_dir/'assets.json').read_text(encoding='utf-8'))
    deno_zip = root/'setup-temp'/'deno.zip'
    fetch(manifest['deno']['deno-'+triple+'.zip'], deno_zip)
    with zipfile.ZipFile(deno_zip) as package:
        filename = 'deno.exe' if os.name == 'nt' else 'deno'
        (root/'tools'/filename).write_bytes(package.read(filename))
        (root/'tools'/filename).chmod(0o755)
    device = 'CPU'
    warnings = []
    if gpu:
        if os.name == 'nt' and has_nvidia():
            log('Installing NVIDIA GPU libraries (about 2 GB installed)…')
            # An installation failure is visible and retryable, never silently skipped.
            run([uv,'pip','install','--python',py,'--only-binary',':all:',*CUDA], env=env)
            probe = "from gpu_runtime import configure_cuda_libraries; configure_cuda_libraries(); import ctypes; [ctypes.WinDLL(x) for x in ('cudart64_12.dll','cublas64_12.dll','cudnn64_9.dll')]; import ctranslate2; assert ctranslate2.get_cuda_device_count()>0; print(ctranslate2.get_supported_compute_types('cuda'))"
            result = subprocess.run([str(py),'-c',probe], cwd=root/'apps'/'local_transcriber', env=env)
            if result.returncode:
                warnings.append('NVIDIA libraries installed, but the GPU check failed. Update your NVIDIA driver. CPU fallback remains available.')
            else:
                device = 'NVIDIA GPU / CUDA, with CPU fallback'
        elif sys.platform == 'darwin' and arch == 'aarch64':
            log('Installing Apple GPU / Metal support…')
            run([uv,'pip','install','--python',py,'--only-binary',':all:',*APPLE], env=env)
            run([py,'-c','import mlx.core as mx; import mlx_whisper; assert mx.metal.is_available(); mx.set_default_device(mx.gpu); print(mx.sum(mx.ones((8,))))'], env=env)
            device = 'Apple GPU / Metal, with CPU fallback'
        else:
            warnings.append('No supported GPU detected. Transcription will use the CPU. Re-run setup after installing an NVIDIA driver if this Windows PC has an NVIDIA GPU.')
    log('Checking both apps and media tools…')
    check_env = dict(env, YTTOOLS_FFMPEG=str(root/'tools'/('ffmpeg.exe' if os.name=='nt' else 'ffmpeg')),
        YTTOOLS_DENO=str(root/'tools'/('deno.exe' if os.name=='nt' else 'deno')), QT_QPA_PLATFORM='offscreen')
    for app in APPS:
        run([py,'-c',"from PySide6.QtWidgets import QApplication; a=QApplication([]); from gui import MainWindow; w=MainWindow(); from dependencies import check_dependencies; e,w=check_dependencies("+str(app=='local_transcriber')+"); assert not e,(e,w); print('App check passed')"], cwd=root/'apps'/app, env=check_env)
    run([py,'-c','import ctranslate2, faster_whisper; print("Local speech engine ready")'], env=env)
    run([root/'tools'/('ffmpeg.exe' if os.name=='nt' else 'ffmpeg'),'-version'], stdout=subprocess.DEVNULL, env=env)
    run([root/'tools'/('deno.exe' if os.name=='nt' else 'deno'),'--version'], env=env)
    state = dict(version='1.1', installed_at=time.strftime('%Y-%m-%d %H:%M:%S'), root=str(root),
                 gpu='auto' if gpu else 'cpu', device=device, warnings=warnings)
    (root/'installation.json').write_text(json.dumps(state, indent=2), encoding='utf-8')
    if sys.platform == 'darwin':
        for app,title in APPS.items():
            mac_bundle(root,app,title)
    # Preserve all dependency metadata/licenses with the installed environment.
    subprocess.run([str(uv),'pip','freeze','--python',str(py)], env=env,
                   stdout=(root/'installed-versions.txt').open('w', encoding='utf-8'), check=True)
    shutil.copy2(assets_dir/'THIRD-PARTY-NOTICES.txt', root/'THIRD-PARTY-NOTICES.txt')
    (root/'READ-ME.txt').write_text(
        'YouTube Local Tools 1.1\n\nOpen either app from this folder.\nDevice: '+device+
        '\n\nInternet is required for YouTube and initial model downloads. Speech inference is local.\n'
        'Downloaded models, temporary work, and output default to the data folder here.\n'
        'You can change these locations in either app. Settings and logs are in settings.\n'
        'Keep the installed folder in place; re-run setup to install somewhere else.\n'
        'Re-run the same setup and choose this folder to repair a failed installation.\n'
        'On Mac, drag the installed folder to Trash to uninstall, after saving anything you want from data.\n'
        'On Windows, open Uninstall YouTube Local Tools.exe; it preserves your data and settings.\n'
        + '\n'.join(warnings)+'\n', encoding='utf-8')
    # Delete only installer-created temporary files inside this exact install root.
    for name in ('setup-temp','setup-cache'):
        directory = root/name
        if directory.resolve().parent == root and directory.is_dir() and not directory.is_symlink():
            try:
                shutil.rmtree(directory)
            except OSError:
                # A Windows GPU driver may hold the temporary directory open
                # until this process exits. This must not invalidate the install.
                log('Some setup temporary files are still in use; they can be removed after setup closes: '+str(directory))
    for warning in warnings:
        log('NOTICE: '+warning)
    log('INSTALLATION COMPLETE. Device: '+device)

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--assets',type=Path,required=True)
    parser.add_argument('--gpu',choices=['auto','cpu'],default='auto')
    args=parser.parse_args()
    try:
        install(args.root,args.assets,args.gpu=='auto')
    except Exception as error:
        log('SETUP FAILED: '+str(error))
        sys.exit(1)
