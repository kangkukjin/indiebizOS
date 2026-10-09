"""훈련자 실행 — HTTP /ibl/execute. 사용: run.py <mode> [--draft shop_v0.ibl] [--check] [--who trainer] [--task-id ID] [--reuse RUN_ID]
mode: base(input→out) · flaky(input_flaky→out_flaky, 서버 --locked) · b(input_b→out_b, 방침만 다름)."""
import argparse, json, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
OUT = HERE.parents[4] / 'outputs/long_sentence_imagination/2026-10-10_48회차'
def main():
    p = argparse.ArgumentParser(); p.add_argument('mode', choices=['base', 'flaky', 'b']); p.add_argument('--draft', default='shop_v0.ibl')
    p.add_argument('--check', action='store_true'); p.add_argument('--who', default='trainer'); p.add_argument('--task-id', default=None); p.add_argument('--reuse', default=None); p.add_argument('--label-suffix', default='')
    a = p.parse_args()
    sub = {'base': ('input', 'out'), 'flaky': ('input_flaky', 'out_flaky'), 'b': ('input_b', 'out_b')}[a.mode]
    src = OUT / a.who / sub[0]; out = OUT / a.who / sub[1]; out.mkdir(parents=True, exist_ok=True)
    request = {'code': (HERE.parent / 'drafts' / a.draft).read_text(), 'origin': 'training', 'project_id': '수동모드', 'check': a.check, 'budget': {'steps': 1000000, 'rows': 100000}, 'inputs': {'src': str(src), 'out': str(out)}}
    if a.task_id: request['task_id'] = a.task_id
    if a.reuse: request['reuse'] = {'run_id': a.reuse}
    label = f'{a.who}_{a.mode}_{Path(a.draft).stem}{"_check" if a.check else ""}{"_reuse" if a.reuse else ""}{a.label_suffix}'
    rp = OUT / 'runs' / f'req_{label}.json'; rp.parent.mkdir(parents=True, exist_ok=True); rp.write_text(json.dumps(request, ensure_ascii=False))
    subprocess.run([sys.executable, str(HERE / 'transport.py'), label, str(rp), '--timeout', '900'], check=True)
if __name__ == '__main__':
    main()
