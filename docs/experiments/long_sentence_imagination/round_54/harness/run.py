"""Run saved IBL over synthetic inputs; preserve all receipts."""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-11_54회차'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('mode')
    p.add_argument('--draft', default='main_v0.ibl')
    p.add_argument('--check', action='store_true')
    p.add_argument('--suffix', default='')
    a = p.parse_args()
    folder = OUT / 'trainer' / a.mode
    payload = dict(code=(HERE.parent / 'drafts' / a.draft).read_text(),
                   project_id='수동모드', origin='training', check=a.check,
                   inputs={'input': str(folder / 'input.json'), 'out': str(folder / 'out')},
                   task_id=f'r54-{a.mode}-{time.time_ns()}')
    label = f'{a.mode}_{Path(a.draft).stem}_{"check" if a.check else "run"}{a.suffix}'
    req = OUT / 'runs' / f'req_{label}.json'
    req.write_text(json.dumps(payload, ensure_ascii=False))
    subprocess.run([sys.executable, str(HERE / 'transport.py'), label, str(req)], check=True)


if __name__ == '__main__':
    main()
