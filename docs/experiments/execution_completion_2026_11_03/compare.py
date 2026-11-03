"""Bounded guide-only crossover; reuse the existing real-provider accounting harness.

Synthetic effects only. This tests authoring feasibility, not overall speedup.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401

SPEC = importlib.util.spec_from_file_location('prior_live', ROOT / 'docs/experiments/episode_5767_repair/live.py')
prior = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prior)
prior.LIMITS.update(model_calls=4, per_call_seconds=90, total_seconds=420,
                    observed_tokens_stop=40000, output_chars=12000)
GRAMMAR = '''IBL edition 2, JSON으로만 응답: {"code":"실행 프로그램"}.
변수 $x, 대입 $x=식, return 식, 레코드 {key:값}, 배열 [1,2], 함수 ($r)=>식,
map(목록,함수), sum(숫자목록), len(목록), assert 조건,"실패설명",진단값.
외부 도구 [fixture:dispatch]{amount:숫자}는 {receipt:문자열,amount:숫자}를 반환.
이 계약 이외 도구/저장 함수/파일/원격 서비스는 없다. 입력은 $rows, $approved 등으로 읽는다.
'''
TASKS = {
    'report_table': '행 $rows의 qty*price를 전부 합쳐 보고서 값 {total:합계,count:행수}를 반환하라. '
                    '빈 입력은 실패여야 한다. 단위는 모두 원이다. 행 예시나 정답값은 주어지지 않는다.',
    'remote_review': '입력 $n의 3배를 시험용 원격 dispatch로 한 번 접수하고 접수증을 보존하라. '
                     '그 뒤 사람이 판단한 $approved가 false이면 접수증을 진단값으로 반환하며 실패, '
                     'true일 때만 그 접수증을 최종 반환하라. 내용 검토 미완료를 성공으로 숨기지 마라.'}


def observe(code, task, root):
    from ibl_v2_adapters import Adapter
    from ibl_v2_entry import handle_request
    effects = []
    def dispatch(runtime, args):
        effects.append(args['amount'])
        return {'receipt': 'fixture-' + str(len(effects)), 'amount': args['amount']}
    registry = {'fixture:dispatch': Adapter({'version': 1, 'params': {'amount': 'Number'},
                'result': 'Record', 'effects': ['write_external']}, dispatch)}
    rows = [{'qty': 2, 'price': 13}, {'qty': 4, 'price': 7}]
    cases = [{'rows': rows}, {'rows': rows + [{'qty': 1, 'price': 9}]}, {'rows': []}] if task == 'report_table' else [
        {'n': 4, 'approved': False}, {'n': 9, 'approved': True}]
    observations = []
    with patch('ibl_v2_adapters.load_registry', lambda *a, **k: registry):
        for index, inputs in enumerate(cases):
            project = root / str(index)
            project.mkdir(parents=True)
            request = {'edition': 2, 'code': code, 'inputs': inputs}
            before = len(effects)
            result = handle_request(request, str(project))
            row = {'inputs': inputs, 'result': result, 'effect_count': len(effects) - before}
            if task == 'remote_review' and index == 0 and result.get('resume'):
                resumed = handle_request({**request, 'resume': result['resume']}, str(project))
                row.update(resumed=resumed, effects_after_resume=len(effects) - before)
            observations.append(row)
    if task == 'report_table':
        passed = all(observations[i]['result'].get('success') and observations[i]['result'].get('value') == expected
                     for i, expected in enumerate([{'total': 54, 'count': 2}, {'total': 63, 'count': 3}]))
        passed = passed and not observations[2]['result'].get('success')
    else:
        first, second = observations
        passed = (not first['result'].get('success') and first.get('effects_after_resume') == 1
                  and not first.get('resumed', {}).get('success') and second['effect_count'] == 1
                  and second['result'].get('success') and second['result'].get('value', {}).get('amount') == 27)
    return {'accepted': bool(passed), 'observations': observations, 'effects': effects}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    prior.isolate(args.output)
    exp = prior.Experiment(args.output)
    guide = (ROOT / 'data/guides/ibl_composition_tools.md').read_text().split('## 판단 경계와 실행 묶음', 1)[1]
    order = [('report_table', 'before'), ('report_table', 'after'), ('remote_review', 'after'), ('remote_review', 'before')]
    exp.manifest.update(order=order, repeats_per_condition_task=1,
                        guide_sha256=hashlib.sha256(guide.encode()).hexdigest(),
                        harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                        input_sha256=hashlib.sha256(json.dumps(TASKS, sort_keys=True).encode()).hexdigest(),
                        comparison='Only appended guide differs; current model/settings, fresh no-tool sessions, synthetic fixed-latency effects.',
                        exclusions=['No statistical performance conclusion at n=1.',
                                    'No real-service latency or complete user workflow measured.',
                                    'Provider usage and elapsed time include the authoring call only.'])
    prior.dump(args.output / 'manifest.json', exp.manifest)  # Before the first call.
    exp.save()
    for index, (task, condition) in enumerate(order):
        key = f'{index}-{task}-{condition}'
        started = time.monotonic()
        try:
            raw = exp.call(exp.provider, GRAMMAR + TASKS[task] + ('\n작성 지침:\n' + guide if condition == 'after' else ''))
            if raw.strip().startswith('```'):
                raw = raw.strip().split('\n', 1)[1].rsplit('```', 1)[0]
            code = json.loads(raw)['code']
            result = observe(code, task, args.output / key)
        except Exception as exc:
            result = {'accepted': False, 'error': type(exc).__name__ + ': ' + str(exc)}
        exp.results[key] = {**result, 'elapsed_s': time.monotonic() - started}
        exp.save()
        print(key, result['accepted'], flush=True)


if __name__ == '__main__':
    main()
