"""훈련자 실행 — HTTP /ibl/execute. 사용: run.py <mode> [--draft main_v0.ibl] [--check] [--who trainer] [--only 이름] [--task-id ID] [--label-suffix S]
mode: base(8941/8942) · flaky(8943/8944). --only 는 신청자 한 명만(동시성 변형: 두 요청을 동시에 보냄)."""
import argparse, json, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
OUT = HERE.parents[4] / 'outputs/long_sentence_imagination/2026-10-09_45회차'

def main():
    p = argparse.ArgumentParser(); p.add_argument('mode', choices=['base', 'flaky']); p.add_argument('--draft', default='main_v0.ibl')
    p.add_argument('--check', action='store_true'); p.add_argument('--who', default='trainer'); p.add_argument('--only', default=None)
    p.add_argument('--task-id', default=None); p.add_argument('--desk', action='store_true'); p.add_argument('--port-override', default=None); p.add_argument('--label-suffix', default='')
    a = p.parse_args()
    src = OUT / a.who / ('input' if a.mode == 'base' else 'input_flaky')
    if a.port_override: src = OUT / a.who / f'input_{a.port_override}'
    out = OUT / a.who / (('out' if a.mode == 'base' else 'out_flaky') + (f'_{a.port_override}' if a.port_override else '') + (f'_{a.only}' if a.only else ''))
    out.mkdir(parents=True, exist_ok=True)
    request = {'code': (HERE.parent / 'drafts' / a.draft).read_text(), 'origin': 'training', 'project_id': '수동모드', 'check': a.check,
               'budget': {'steps': 1000000, 'rows': 100000}, 'inputs': {'src': str(src), 'out': str(out), 'only': a.only, 'desk': a.desk}}
    if a.task_id: request['task_id'] = a.task_id
    label = f'{a.who}_{a.mode}_{Path(a.draft).stem}{"_check" if a.check else ""}{"_" + a.port_override if a.port_override else ""}{"_" + a.only if a.only else ""}{a.label_suffix}'
    rp = OUT / 'runs' / f'req_{label}.json'; rp.parent.mkdir(parents=True, exist_ok=True); rp.write_text(json.dumps(request, ensure_ascii=False))
    subprocess.run([sys.executable, str(HERE / 'transport.py'), label, str(rp), '--timeout', '1500'], check=True)

if __name__ == '__main__':
    main()
