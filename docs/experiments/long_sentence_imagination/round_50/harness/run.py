"""훈련자 실행 — HTTP /ibl/execute. 사용: run.py <mode> [--draft queue_v0.ibl] [--check] [--who trainer] [--task-id ID] [--label-suffix S]
mode: base · a(깨진 사진 1장+느린 변환) · b(job.json 만 다름, 사진 3배)."""
import argparse, json, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
OUT = HERE.parents[4] / 'outputs/long_sentence_imagination/2026-10-10_50회차'
def main():
    p = argparse.ArgumentParser(); p.add_argument('mode', choices=['base', 'a', 'b']); p.add_argument('--draft', default='queue_v0.ibl')
    p.add_argument('--check', action='store_true'); p.add_argument('--who', default='trainer'); p.add_argument('--task-id', default=None); p.add_argument('--label-suffix', default='')
    a = p.parse_args()
    src = OUT / a.who / a.mode / 'input'; out = OUT / a.who / a.mode / 'out'; out.mkdir(parents=True, exist_ok=True)
    request = {'code': (HERE.parent / 'drafts' / a.draft).read_text(), 'origin': 'training', 'project_id': '수동모드', 'check': a.check, 'inputs': {'src': str(src), 'out': str(out)}}
    if a.task_id: request['task_id'] = a.task_id
    label = f'{a.who}_{a.mode}_{Path(a.draft).stem}{"_check" if a.check else ""}{a.label_suffix}'
    rp = OUT / 'runs' / f'req_{label}.json'; rp.parent.mkdir(parents=True, exist_ok=True); rp.write_text(json.dumps(request, ensure_ascii=False))
    subprocess.run([sys.executable, str(HERE / 'transport.py'), label, str(rp), '--timeout', '1500'], check=True, stdout=subprocess.DEVNULL)
    subprocess.run([sys.executable, str(HERE / 'show.py'), label], check=True)
if __name__ == '__main__':
    main()
