"""훈련자 실행 — HTTP /ibl/execute. 사용: run.py <mode> [--draft main_v0.ibl] [--check] [--who trainer] [--reuse RUN_ID]
mode: base(input→out) · react(input→out, 변형: 반응 자료 도착 뒤 두 번째 프로그램)"""
import argparse, json, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
OUT = HERE.parents[4] / 'outputs/long_sentence_imagination/2026-10-09_43회차'

def main():
    p = argparse.ArgumentParser(); p.add_argument('mode', choices=['base', 'react']); p.add_argument('--draft', default='main_v0.ibl')
    p.add_argument('--check', action='store_true'); p.add_argument('--who', default='trainer'); p.add_argument('--reuse', default=None)
    a = p.parse_args()
    (OUT / a.who / 'out').mkdir(parents=True, exist_ok=True)
    request = {'code': (HERE.parent / 'drafts' / a.draft).read_text(), 'origin': 'training', 'project_id': '수동모드', 'check': a.check,
               'budget': {'steps': 1000000, 'rows': 100000},
               'inputs': {'src': str(OUT / a.who / 'input'), 'out': str(OUT / a.who / 'out')}}
    if a.reuse:
        request['reuse'] = {'run_id': a.reuse}
    rp = OUT / 'runs' / f'req_{a.mode}_{Path(a.draft).stem}{"_check" if a.check else ""}.json'; rp.parent.mkdir(parents=True, exist_ok=True); rp.write_text(json.dumps(request, ensure_ascii=False))
    label = f'{a.who}_{a.mode}_{Path(a.draft).stem}{"_check" if a.check else ""}{"_reuse" if a.reuse else ""}'
    subprocess.run([sys.executable, str(HERE / 'transport.py'), label, str(rp), '--timeout', '1500'], check=True)

if __name__ == '__main__':
    main()
