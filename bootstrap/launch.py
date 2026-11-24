"""Installed app entry point; safe with multiprocessing's spawn mode."""
import json
import multiprocessing
import os
from pathlib import Path
import runpy
import sys

def main():
    root = Path(__file__).resolve().parent
    app = sys.argv[1] if len(sys.argv)>1 else ''
    if app not in ('screenshot_pdf','local_transcriber'):
        raise SystemExit('Choose one of the installed apps.')
    os.environ['YTTOOLS_CONFIG_ROOT'] = str(root/'settings')
    os.environ['YTTOOLS_DATA_ROOT'] = str(root/'data')
    state = json.loads((root/'installation.json').read_text(encoding='utf-8'))
    os.environ['YTTOOLS_GPU'] = state.get('gpu','auto')
    for tool in ('ffmpeg','deno'):
        os.environ['YTTOOLS_'+tool.upper()] = str(root/'tools'/(tool+('.exe' if os.name=='nt' else '')))
    os.environ['PATH'] = str(root/'tools')+os.pathsep+os.environ.get('PATH','')
    sys.path.insert(0,str(root/'apps'/app))
    runpy.run_path(str(root/'apps'/app/'main.py'),run_name='__main__')

if __name__ == '__main__':
    multiprocessing.freeze_support()
    main()
