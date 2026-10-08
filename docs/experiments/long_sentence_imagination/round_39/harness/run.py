"""훈련자 실행 — HTTP /ibl/execute 만 사용. 사용: run.py <mode> [--draft main_v0.ibl] [--check] [--no-apply]
mode: base(trainer/docs→out) · again(같은 폴더 재실행→out_again) · bad(trainer/docs_bad→out_bad) · dry(trainer/docs, apply:false→out_dry)"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-09_39회차'
TERMS = [{"old": "구독 플랜", "new": "요금제"}, {"old": "워크스페이스", "new": "작업 공간"}]
MODES = {
    'base': ('docs', 'out', True), 'again': ('docs', 'out_again', True),
    'bad': ('docs_bad', 'out_bad', True), 'dry': ('docs_dry', 'out_dry', False),
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=MODES)
    p.add_argument('--draft', default='main_v0.ibl')
    p.add_argument('--check', action='store_true')
    p.add_argument('--who', default='trainer')
    a = p.parse_args()
    docs, out, apply = MODES[a.mode]
    code = (HERE.parent / 'drafts' / a.draft).read_text()
    (OUT / a.who / out).mkdir(parents=True, exist_ok=True)
    request = {'code': code, 'origin': 'training', 'project_id': '수동모드', 'check': a.check,
               'budget': {'steps': 1000000, 'rows': 100000},
               'inputs': {'docs': str(OUT / a.who / docs), 'out': str(OUT / a.who / out), 'terms': TERMS, 'apply': apply}}
    req_path = OUT / 'runs' / f'req_{a.mode}_{Path(a.draft).stem}{"_check" if a.check else ""}.json'
    req_path.parent.mkdir(parents=True, exist_ok=True)
    req_path.write_text(json.dumps(request, ensure_ascii=False))
    label = f'{a.who}_{a.mode}_{Path(a.draft).stem}{"_check" if a.check else ""}'
    subprocess.run([sys.executable, str(HERE / 'transport.py'), label, str(req_path)], check=True)


if __name__ == '__main__':
    main()
