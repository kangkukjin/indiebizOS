"""훈련자 실행 — HTTP /ibl/execute. 사용: run.py <mode> [--draft main_v0.ibl] [--check] [--who trainer] [--reuse RUN_ID]
mode: base(base→out) · v1(v1→out1, prev=out) · v2(v2→out2) · v3(v3→out3)"""
import argparse, json, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
OUT = HERE.parents[4] / 'outputs/long_sentence_imagination/2026-10-09_41회차'
MODES = {'base': ('base', 'out', None), 'v1': ('v1', 'out1', 'out'), 'v1b': ('base', 'out1b', 'out'), 'v2': ('v2', 'out2', None), 'v3': ('v3', 'out3', None)}  # v1b = 정정 7파일을 base 에 제자리 덮어쓴 뒤 reuse

def main():
    p = argparse.ArgumentParser(); p.add_argument('mode', choices=MODES); p.add_argument('--draft', default='main_v0.ibl')
    p.add_argument('--check', action='store_true'); p.add_argument('--who', default='trainer'); p.add_argument('--reuse', default=None)
    a = p.parse_args(); src, out, prev = MODES[a.mode]
    (OUT / a.who / out).mkdir(parents=True, exist_ok=True)
    request = {'code': (HERE.parent / 'drafts' / a.draft).read_text(), 'origin': 'training', 'project_id': '수동모드', 'check': a.check,
               'budget': {'steps': 1000000, 'rows': 100000},
               'inputs': {'src': str(OUT / a.who / src), 'out': str(OUT / a.who / out), 'prev': str(OUT / a.who / prev) if prev else None}}
    if a.reuse:
        request['reuse'] = {'run_id': a.reuse}   # 응답 continuation.reuse_args 의 내용을 최상위에 병합
    rp = OUT / 'runs' / f'req_{a.mode}_{Path(a.draft).stem}{"_check" if a.check else ""}.json'; rp.parent.mkdir(parents=True, exist_ok=True); rp.write_text(json.dumps(request, ensure_ascii=False))
    label = f'{a.who}_{a.mode}_{Path(a.draft).stem}{"_check" if a.check else ""}{"_reuse" if a.reuse else ""}'
    subprocess.run([sys.executable, str(HERE / 'transport.py'), label, str(rp)], check=True)

if __name__ == '__main__':
    main()
