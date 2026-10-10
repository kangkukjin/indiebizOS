"""훈련자 실행 — 사용: run.py <evening|morning> <mode> [--draft F] [--check] [--who trainer] [--label-suffix S]. 저녁·아침은 서로 다른 task_id(잇는 것은 out/receipt.json 뿐)."""
import argparse, json, subprocess, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
OUT = HERE.parents[4] / 'outputs/long_sentence_imagination/2026-10-11_51회차'
def main():
    p = argparse.ArgumentParser(); p.add_argument('part', choices=['evening', 'morning']); p.add_argument('mode'); p.add_argument('--draft', default=None)
    p.add_argument('--check', action='store_true'); p.add_argument('--who', default='trainer'); p.add_argument('--label-suffix', default='')
    a = p.parse_args(); draft = a.draft or ('morning_v1.ibl' if a.part == 'morning' else 'evening_v1.ibl')
    src = OUT / a.who / a.mode / 'input'; out = OUT / a.who / a.mode / 'out'
    request = {'code': (HERE.parent / 'drafts' / draft).read_text(), 'origin': 'training', 'project_id': '수동모드', 'check': a.check, 'inputs': {'src': str(src), 'out': str(out)}, 'task_id': f'r51-{a.who}-{a.mode}-{a.part}-{int(time.time())}'}
    label = f'{a.who}_{a.mode}_{Path(draft).stem}{"_check" if a.check else ""}{a.label_suffix}'
    rp = OUT / 'runs' / f'req_{label}.json'; rp.write_text(json.dumps(request, ensure_ascii=False))
    subprocess.run([sys.executable, str(HERE / 'transport.py'), label, str(rp), '--timeout', '900'], check=True, stdout=subprocess.DEVNULL)
    subprocess.run([sys.executable, str(HERE / 'show.py'), label, '3500'], check=True)
if __name__ == '__main__':
    main()
