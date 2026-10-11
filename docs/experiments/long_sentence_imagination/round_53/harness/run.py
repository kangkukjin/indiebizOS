"""훈련자 실행 — 사용: run.py <mode> [--draft F] [--check] [--who trainer] [--keep-out] [--reuse RUN_ID] [--suffix S]. out 폴더는 실행 전 비운다(--keep-out 이면 그대로)."""
import argparse, json, shutil, subprocess, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
OUT = HERE.parents[4] / 'outputs/long_sentence_imagination/2026-10-11_53회차'
def main():
    p = argparse.ArgumentParser(); p.add_argument('mode'); p.add_argument('--draft', default='main_v0.ibl'); p.add_argument('--check', action='store_true')
    p.add_argument('--who', default='trainer'); p.add_argument('--keep-out', action='store_true'); p.add_argument('--reuse', default=None); p.add_argument('--suffix', default=''); p.add_argument('--default-budget', action='store_true')
    a = p.parse_args(); src = OUT / a.who / a.mode / 'input'; out = OUT / a.who / a.mode / 'out'
    if not a.check and not a.keep_out: shutil.rmtree(out, ignore_errors=True); out.mkdir()
    request = {'code': (HERE.parent / 'drafts' / a.draft).read_text(), 'origin': 'training', 'project_id': '수동모드', 'check': a.check, 'inputs': {'src': str(src), 'out': str(out)},
               'budget': {'steps': 2000000, 'rows': 50000}, 'task_id': f'r53-{a.who}-{a.mode}-{int(time.time())}'}
    if a.default_budget: request.pop('budget')
    if a.reuse: request['reuse'] = {'run_id': a.reuse}
    label = f'{a.who}_{a.mode}_{Path(a.draft).stem}{"_check" if a.check else ""}{a.suffix}'
    rp = OUT / 'runs' / f'req_{label}.json'; rp.write_text(json.dumps(request, ensure_ascii=False))
    subprocess.run([sys.executable, str(HERE / 'transport.py'), label, str(rp), '--timeout', '900'], check=True, stdout=subprocess.DEVNULL)
    subprocess.run([sys.executable, str(HERE / 'show.py'), label, '4500'], check=True)
if __name__ == '__main__':
    main()
