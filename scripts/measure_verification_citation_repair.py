#!/usr/bin/env python3
"""Paired real-evaluator regression, using isolated fictional research and existing model settings."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401

import argparse
import base64
import importlib.abc
import importlib.util
import io
import json
import subprocess
import time
from contextlib import nullcontext
from types import SimpleNamespace

BASELINE = '2f34b274644ff601736e06010b497644305687b7'
WORK = ROOT / 'data/_backups/2026-11-05_verification_citation_model'
REPORT = ROOT / 'docs/experiments/verification_citation_repair_2026_11_05.json'
MODULES = {
    'research_context': 'base', 'research_review': 'base', 'thread_context': 'base',
    'research_capture': 'services', 'research_library': 'services',
    'research_evidence': 'datastore', 'research_store': 'datastore', 'supervision_store': 'datastore',
    'supervisor_content': 'cognition', 'cognitive_eval': 'cognition',
    'final_evaluator': 'cognition', 'evaluation_input': 'cognition',
}


class Baseline(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Load committed module bytes without a checkout, clone, or production writes."""
    def find_spec(self, fullname, path=None, target=None):
        if fullname in MODULES:
            return importlib.util.spec_from_loader(fullname, self)

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        name = f'backend/{MODULES[module.__name__]}/{module.__name__}.py'
        source = subprocess.check_output(['git', 'show', f'{BASELINE}:{name}'], cwd=ROOT)
        module.__file__ = str(ROOT / name)
        exec(compile(source, module.__file__, 'exec'), module.__dict__)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def worker(args):
    if args.arm == 'baseline':
        sys.meta_path.insert(0, Baseline())
    import research_capture  # noqa: F401
    from research_context import scope
    from research_store import ResearchStore
    from research_library import ResearchLibrary
    from supervision_store import TurnStore
    from final_evaluator import prepare, invoke, snapshot_error
    from evaluation_input import evidence_requests, new_evidence_requests, recover
    from consciousness_agent import _resolve_oneshot_provider
    model = _resolve_oneshot_provider('evaluate')
    if args.arm == 'baseline':
        from cognitive_eval import CognitiveEvalMixin
        original_prompt = subprocess.check_output(['git', 'show', f'{BASELINE}:data/common_prompts/evaluator_prompt.md'], cwd=ROOT).decode()
        CognitiveEvalMixin._load_evaluator_prompt = classmethod(lambda cls: original_prompt)
    directory = WORK / f'{args.case}-{args.repeat}-{args.arm}'
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'research').mkdir(exist_ok=True)
    store = ResearchStore(directory / 'research', 'fixture-project')
    tid = store.create_thread('합성 검수 시험')['id']
    lib = ResearchLibrary(store, tid)
    ref = lib.capture('원문', title='계약 집계', paragraphs=[
        ('p1', '2026-11-01 계약 목표는 100건이다. 실제 체결 건수는 확인되지 않았다.'),
        ('p2', '비교 실험의 평균 차이는 0이었다. 인과적 개선은 입증되지 않았다.')])
    vid = ref['version_ref']
    with scope({'project_uid': store.uid, 'run_id': 'previous'}):
        lib.read(vid)
    run, _ = store.begin_run(tid, '원문에 충실한 간단한 보고서 작성', 'fixture-request')
    context = {'project_uid': store.uid, 'thread_id': tid, 'run_id': run,
               'path': str(store.path), 'epoch': store.epoch, 'mode': 'research'}
    workbench = TurnStore(directory / 'turn')
    controller = SimpleNamespace(store=workbench, project_path=str(directory),
        message='원문에 근거해 계약 목표와 실제 체결 실적을 구별하고 효과의 한계를 설명해 줘. 인용 표기 예시도 한 줄 설명해 줘.',
        framing={'achievement_criteria': '최종 보고서가 원문의 목표와 실적을 구별하며 효과 미확인을 보존한다. 실제 인용은 유효 원문에 연결되고 표기 예시는 예시로 구별한다.'},
        history=[], job_states={}, last_decision=None, delivery=SimpleNamespace(manifest=lambda: None),
        cancelled=lambda: False, evaluation_stage=lambda stage: nullcontext(),
        log=lambda kind, **kw: workbench.log(kind, **kw), phase_usage={},
        usage={'input': 0, 'output': 0}, final_usage={'input': 0, 'output': 0})
    report = directory / 'report.md'
    normal = (f'계약 목표는 100건이고 실제 체결 실적은 미확인이다. [자료:{vid}:p1]\n'
              f'비교 실험에서 인과적 개선은 입증되지 않았다. [자료:{vid}:p2]\n'
              '인용 표기 예시: `[자료:판본:위치]`는 구체적인 원문 주소로 채워 사용한다.')
    report.write_text(normal)
    calls = [{'name': 'Write', 'input': {'path': str(report)}, 'result': 'saved'}]
    workbench.put_response(f'[최종 보고서]({report})')
    with scope(context):
        if args.case in {'mixed_invalid', 'changed_conclusion'}:
            lib.read(vid)
        if args.case == 'mixed_invalid':
            report.write_text(normal + f'\n실제 체결은 999건으로 확인됐다. [자료:{vid}:p9]')
        elif args.case == 'changed_conclusion':
            prepare(controller, calls)
            report.write_text(normal.replace('실제 체결 실적은 미확인이다', '실제 체결 실적은 100건으로 확정됐다'))
        elif args.case in {'native_image', 'wrong_image', 'empty_capture'}:
            from PIL import Image, ImageDraw
            picture = Image.new('RGB', (640, 360), 'white')
            ImageDraw.Draw(picture).text((100, 130), 'STATUS: READY', fill='black', font_size=40)
            stream = io.BytesIO(); picture.save(stream, format='PNG')
            calls = [{'name': 'view_image', 'input': {}, 'result': [
                {'type': 'image', 'mimeType': 'image/png', 'data': base64.b64encode(stream.getvalue()).decode()}]}]
            controller.message = '첨부된 시험 화면의 상태가 READY인지 직접 확인해 알려줘.'
            controller.framing = {'achievement_criteria': '실제 화면의 상태를 보고 READY 여부를 정확히 보고한다.'}
            block = workbench.blocks[0]
            workbench.patch(workbench.version, [{'id': block['id'], 'hash': block['hash'],
                                                 'text': '첨부된 시험 화면의 상태는 ERROR입니다.' if args.case == 'wrong_image' else '첨부된 시험 화면의 상태는 READY입니다.'}])
        if args.case == 'empty_capture':
            calls = [{'name': 'exec_command', 'input': {'cmd': 'capture-screen > screen.png'},
                      'result': {'stdout': '', 'exit_code': 0}}]
        started = time.monotonic()
        packet = prepare(controller, calls)
        preparation_s = time.monotonic() - started
        decisions = []
        for _ in range(3):
            decision = json.loads(invoke(controller))
            decisions.append(decision)
            if decision['status'] != 'UNKNOWN' or not decision.get('recoverable'):
                break
            parsed = evidence_requests(decision['reason'], packet)
            requests = new_evidence_requests(parsed['requests'], packet.get('attachments', []))
            if not requests:
                break
            packet['attachments'].extend(recover(controller, requests))
        changed = snapshot_error(controller)
        if changed:
            raise RuntimeError(changed)
        if args.arm == 'candidate':
            from research_context import finish_review
            outcome = finish_review(workbench.text, {
                'review_status': decision['status'], 'goal_status': decision.get('goal_status', 'UNKNOWN'),
                'reason': decision.get('reason', '')}, decision.get('citation_uses', []))
            store.write_response(tid, run, workbench.text, 'completed', outcome=outcome)
        else:
            store.write_response(tid, run, workbench.text, 'completed', lib.citations(workbench.text, run))
        elapsed_s = time.monotonic() - started
        result = {'case': args.case, 'repeat': args.repeat, 'arm': args.arm, 'model': model.model,
                  'baseline': BASELINE, 'expected': 'REWORK' if args.case in {'mixed_invalid', 'changed_conclusion', 'wrong_image'} else 'UNKNOWN' if args.case == 'empty_capture' else 'APPROVED',
                  'status': decision['status'], 'decisions': decisions, 'calls': len(decisions),
                  'usage': controller.final_usage, 'preparation_s': preparation_s, 'elapsed_s': elapsed_s,
                  'image_count': len(packet['images']), 'artifact_count': len(controller.content_artifacts),
                  'stored_unchanged': store.messages(tid)['items'][-1]['content'] == workbench.text}
        write(directory / 'result.json', result)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', required=True)
    parser.add_argument('--arm', choices=['baseline', 'candidate'])
    parser.add_argument('--case', default='retained_example')
    parser.add_argument('--repeat', type=int, default=0)
    parser.add_argument('--repetitions', type=int, default=3)
    args = parser.parse_args()
    if args.arm:
        worker(args)
        return
    results = []
    for case in ('retained_example', 'mixed_invalid', 'changed_conclusion', 'native_image', 'wrong_image', 'empty_capture'):
        for repeat in range(args.repetitions):
            for arm in (('baseline', 'candidate') if repeat % 2 == 0 else ('candidate', 'baseline')):
                print(f'{case} {repeat} {arm}', flush=True)
                if not (WORK / f'{case}-{repeat}-{arm}/result.json').exists():
                    subprocess.run([sys.executable, __file__, '--live', '--case', case,
                                    '--repeat', str(repeat), '--arm', arm], check=True, cwd=ROOT)
                result = json.loads((WORK / f'{case}-{repeat}-{arm}/result.json').read_text())
                results.append(result)
                write(REPORT, {'baseline': BASELINE, 'cases': results,
                    'limits': ['Fixed synthetic evidence and configured real evaluator; no external research or notification.',
                               'Isolated input, evaluation, recovery and storage timing; not an end-to-end open research benchmark.']})
                print(json.dumps({k: result[k] for k in ('case', 'arm', 'status', 'calls', 'usage', 'elapsed_s')}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
