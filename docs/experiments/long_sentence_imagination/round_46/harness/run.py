"""훈련자 실행 — HTTP /ibl/execute. 사용: run.py <mode> <call> [--draft compare_v0.ibl] [--check] [--who trainer] [--task-id ID] [--reuse RUN_ID] [--desk] [--choice ROOM] [--ref RESULT_REF_ID]
mode: base(input→out) · flaky(input_flaky→out_flaky) · b(input_b→out_b). call: 1(비교) · 2(보류·미리보기). 같은 task_id 로 두 호출을 잇는다."""
import argparse, json, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
OUT = HERE.parents[4] / 'outputs/long_sentence_imagination/2026-10-09_46회차'
def main():
    p = argparse.ArgumentParser(); p.add_argument('mode', choices=['base', 'flaky', 'b', 'exp']); p.add_argument('call', choices=['1', '2']); p.add_argument('--draft', default=None)
    p.add_argument('--check', action='store_true'); p.add_argument('--who', default='trainer'); p.add_argument('--task-id', default=None); p.add_argument('--reuse', default=None)
    p.add_argument('--desk', action='store_true'); p.add_argument('--choice', default=None); p.add_argument('--ref', default=None); p.add_argument('--label-suffix', default='')
    a = p.parse_args()
    sub = {'base': ('input', 'out'), 'flaky': ('input_flaky', 'out_flaky'), 'b': ('input_b', 'out_b'), 'exp': ('input_exp', 'out_exp')}[a.mode]
    src = OUT / a.who / sub[0]; out = OUT / a.who / sub[1]; out.mkdir(parents=True, exist_ok=True)
    draft = a.draft or ('compare_v0.ibl' if a.call == '1' else 'hold_v0.ibl')
    inputs = {'src': str(src), 'out': str(out)}
    if a.call == '2':
        inputs['desk'] = a.desk; inputs['choice'] = a.choice
        if a.ref: inputs['compare'] = {'$ref': a.ref}
        else: inputs['compare'] = json.loads((out / 'compare.json').read_text())   # 1차 산출 파일을 값으로 연결(참조가 없을 때)
    request = {'code': (HERE.parent / 'drafts' / draft).read_text(), 'origin': 'training', 'project_id': '수동모드', 'check': a.check, 'budget': {'steps': 1000000, 'rows': 100000}, 'inputs': inputs}
    if a.task_id: request['task_id'] = a.task_id
    if a.reuse: request['reuse'] = {'run_id': a.reuse}
    label = f'{a.who}_{a.mode}_call{a.call}_{Path(draft).stem}{"_check" if a.check else ""}{"_reuse" if a.reuse else ""}{a.label_suffix}'
    rp = OUT / 'runs' / f'req_{label}.json'; rp.parent.mkdir(parents=True, exist_ok=True); rp.write_text(json.dumps(request, ensure_ascii=False))
    subprocess.run([sys.executable, str(HERE / 'transport.py'), label, str(rp), '--timeout', '1500'], check=True)
if __name__ == '__main__':
    main()
