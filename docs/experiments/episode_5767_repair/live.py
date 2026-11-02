"""Bounded real-model acceptance; all mutable stores are isolated under --output.

Run with the repository .venv Python. Fresh no-tools model sessions choose IBL
programs and steering coordinates. The harness executes their decisions through
production APIs; expected values never enter those prompts. No live user tasks
or function catalog are changed. Raw artifacts stay in ignored data/outputs.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401

import argparse
import copy
import hashlib
import json
import os
import signal
import sqlite3
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

LIMITS = {'model_calls': 10, 'per_call_seconds': 180, 'total_seconds': 1500,
          'input_bytes_per_call': 32000, 'observed_tokens_stop': 100000,
          'output_chars': 12000}
GRAMMAR = '''IBL edition=2. JSON으로만 답하라. IBL의 일반 문법:
[def:이름]($인자,$기본=0){return $인자+$기본}; [fn:이름]{인자:3};
$x=식; return {key:$x}; 산술 + - * /, 배열 [1,2], 레코드 {x:1}, 필드 $r.x.
함수명·인자명은 직접 정한다. 호출자는 선언된 명명 인자를 쓴다.
외부 도구나 파일은 쓰지 마라. 기존 계약으로 충분하면 기존 함수를 호출할 수 있다.
'''


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def isolate(directory):
    os.environ['INDIEBIZ_RUNTIME_STATE_DIR'] = str(directory / 'runtime')
    os.environ['INDIEBIZ_RECALL_INDEX_DIR'] = str(directory / 'recall_index')
    import workflow_store
    import script_workspace
    import episode_logger
    import ibl_usage_db
    import ibl_usage_rag
    import ibl_idiom
    import hippo_tree
    workflows = directory / 'workflows'
    workflows.mkdir(parents=True)
    workflow_store._get_workflows_path = lambda: workflows
    script_workspace.storage_root = lambda: directory / 'scripts'
    def connect():
        conn = sqlite3.connect(directory / 'episodes.db', timeout=10)
        conn.row_factory = sqlite3.Row
        return conn
    episode_logger._get_db = connect
    episode_logger._ensure_episode_tables()
    ibl_usage_db.DB_PATH = str(directory / 'usage.db')
    ibl_usage_db.IBLUsageDB._instance = None
    # Match the repository's isolated_distill_training fixture. Projection paths
    # change, not eligibility, selection or storage behavior.
    target = directory / 'data/common_prompts/reflection_prompt.md'
    target.parent.mkdir(parents=True)
    target.write_bytes((ROOT / 'data/common_prompts/reflection_prompt.md').read_bytes())
    (directory / 'data/training').mkdir(parents=True)
    ibl_usage_rag.__file__ = str(directory / 'backend/cognition/ibl_usage_rag.py')
    ibl_idiom.__file__ = str(directory / 'backend/cognition/ibl_idiom.py')
    hippo_tree.DOC_DIR = str(directory / 'hippocampus_tree')
    hippo_tree.GUIDE_DB_PATH = str(directory / 'guide_db.json')
    return ibl_usage_db.IBLUsageDB()


class Experiment:
    def __init__(self, directory):
        import consciousness_agent as ca
        self.directory = directory
        self.started = time.monotonic()
        self.original = ca.call_oneshot_provider
        self.provider = copy.copy(ca._resolve_oneshot_provider('evaluate'))
        if self.provider is None or not self.provider.is_ready:
            raise RuntimeError('configured evaluator is unavailable')
        self.provider.request_limits = {'chars': 30000, 'bytes': LIMITS['input_bytes_per_call']}
        self.provider.project_path = str(directory)
        self.provider.system_prompt = ''
        self.provider.STREAM_IDLE_TIMEOUT_SEC = 120
        self.provider.DEFAULT_TIMEOUT_SEC = 180
        self.provider.max_tokens = 3000
        self.calls, self.results = [], {}
        self.manifest = {'limits': LIMITS, 'provider': type(self.provider).__name__,
            'harness_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'model': self.provider.model, 'fresh_history': True, 'isolated_stores': True,
            'token_policy': 'Measured token stop between calls; provider output cap is adapter-dependent. '
                            'One call can overshoot the measured stop. Unreported usage is unknown.',
            'method': 'Synthetic tasks, real provider and production compile/store/search/control/review. '
                      'No expected result or selected function name is given to later sessions.'}
        dump(directory / 'manifest.json', self.manifest)

    def save(self):
        dump(self.directory / 'result.json', {'manifest': self.manifest, 'calls': self.calls,
             'results': self.results, 'elapsed_s': time.monotonic() - self.started})

    def call(self, provider, prompt, **kwargs):
        import consciousness_agent as ca
        usage, started = {}, time.monotonic()
        measured = sum((c['usage'].get('total_input_tokens') or 0) +
                       (c['usage'].get('total_output_tokens') or 0) for c in self.calls)
        if len(self.calls) >= LIMITS['model_calls'] or measured >= LIMITS['observed_tokens_stop']:
            raise RuntimeError('model budget exhausted')
        if started - self.started > LIMITS['total_seconds']:
            raise RuntimeError('experiment deadline')
        prepare = getattr(prompt, 'prepare_request', None)
        planned = prompt
        if prepare:
            planning_provider = copy.copy(self.provider)
            planning_provider.system_prompt = kwargs.get('system_prompt', self.provider.system_prompt)
            planned = prepare(planning_provider)
        if len(str(planned).encode()) > LIMITS['input_bytes_per_call']:
            raise RuntimeError('input byte budget exceeded')
        kwargs.pop('usage_sink', None)
        def deadline(*_):
            raise TimeoutError('acceptance call deadline')
        previous = signal.signal(signal.SIGALRM, deadline)
        signal.alarm(LIMITS['per_call_seconds'])
        answer, error = None, None
        from model_call_context import capture_usage
        try:
            with capture_usage() as billable:
                answer = self.original(self.provider, prompt, **kwargs, usage_sink=usage)
        except Exception as exc:
            error = type(exc).__name__ + ': ' + str(exc)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)
            self.calls.append({'prompt': str(planned), 'answer': answer, 'usage': usage,
                               'billable': billable,
                               'elapsed_s': time.monotonic() - started, 'error': error,
                               'failure': ca.oneshot_failure_details()})
            self.save()
        if not answer or len(answer) > LIMITS['output_chars']:
            raise RuntimeError(error or 'model output missing/excessive')
        return answer

    def choose(self, request):
        raw = self.call(self.provider, GRAMMAR + request)
        if raw.strip().startswith('```'):
            raw = raw.strip().split('\n', 1)[1].rsplit('```', 1)[0]
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError('model decision must be object')
        return result

    def reuse(self, db):
        from ibl_v2_store import action, _describe
        from ibl_v2_entry import handle_request
        from ibl_usage_rag import _exec_detail
        from associative_recall import _used_hippocampus
        # First independent session authors its own reusable function.
        authored = self.choose('계측 장치의 원시값 raw에 영점 zero를 빼고 gain을 곱해 보정한다. '
            '이 계산을 재사용 가능한 함수 하나로 만들고 raw=18, zero=3, gain=4에 실행하라. '
            '출력 JSON: {"definition":"IBL 정의 하나", "description":"용도와 단위 제약", "code":"실행 프로그램"}.')
        saved = action('save', {'code': authored['definition'], 'description': authored['description']}, str(self.directory))
        if not saved.get('success'):
            raise RuntimeError('registration failed: ' + str(saved))
        first = handle_request({'edition': 2, 'code': authored['code']}, str(self.directory))
        self.results['author'] = {'saved': saved, 'execution': first, 'correct': first.get('value') == 60}
        # Actual catalog/name search; no embeddings/network dependency for this controlled lexical fixture.
        from ibl_name_search import search_aliased
        rows = search_aliased(db, '계측 보정 원시값 영점 gain raw zero', alpha=0)
        cards = [{'intent': r.intent, 'name': r.alias, 'contract': _describe(r.alias)} for r in rows]
        self.results['discovery'] = {'cards': cards, 'method': 'production search_aliased, alpha=0'}
        presented = _exec_detail('', 0, '', phrases=rows)['presented']
        for case, question, expected in [
            ('changed_input', '계측 원시값 31, 영점 7, gain 3을 보정하라.', 72),
            ('composition', '두 센서의 원시값 31과 22를 각각 영점 7, gain 3으로 보정하고, '
                            '그 차이를 duration=9로 나눈 변화율을 별도 지역 함수와 조합해 구하라.', 3),
        ]:
            decision = self.choose(question + '\n검색된 현재 계약=' + json.dumps(cards, ensure_ascii=False) +
                                   '\n출력 {"code":"IBL 실행 프로그램", "reason":"선택 이유"}.')
            output = handle_request({'edition': 2, 'code': decision['code']}, str(self.directory))
            use = _used_hippocampus([], {'items': presented}, {'ibl_codes': [decision['code']],
                'tool_calls': [{'input': {'code': decision['code']}, 'result': output}]})
            self.results[case] = {'decision': decision, 'execution': output, 'recall_usage': use,
                                  'correct': output.get('success') and (output.get('value') == expected or
                                      case == 'composition' and output.get('value') == {'first': 72, 'second': 45, 'rate': 3}),
                                  'reused_current': bool(use['successful'])}
            self.save()
        # Existing 0/1 selector chooses verified source IDs or nothing; no forced learning.
        import unified_distill as distill
        row = self.results['composition']
        job = {'user_message': '두 센서 보정 후 차이를 시간으로 나눠 변화율을 구한다.',
               'write_deep': False, 'write_forage': False, 'hippo_score': 0,
               'tool_calls': [{'tool_name': 'execute_ibl', 'input': {'edition': 2, 'code': row['decision']['code']},
                               'result': row['execution'], 'success': row['execution'].get('success')}]}
        prepared = distill.fit_input(distill.prepare(job))
        distilled = {'skip_reasons': prepared['skip_reasons'], 'saved': []}
        if prepared['sections']:
            answer = self.call(self.provider, json.dumps(distill.model_input(prepared), ensure_ascii=False),
                               system_prompt=distill.SYSTEM_PROMPT, step_role='unified_distill')
            decision = distill.parse_decision(answer)
            distilled['decision'] = decision
            for index, candidate in enumerate(decision['execution']):
                key = distill.fingerprint(['acceptance', index, candidate])
                distilled['saved'].append(distill._apply(job, prepared, 'execution', candidate, key))
        with db._get_connection() as conn:
            distilled['stored_rows'] = [dict(r) for r in conn.execute(
                'SELECT id,intent,ibl_code,alias,source,provenance FROM ibl_current_examples')]
        self.results['distillation'] = distilled
        self.save()
        # Same model/materials without accumulated catalog; genuinely separate definition scope.
        import workflow_store
        blank = self.directory / 'baseline_workflows'
        blank.mkdir()
        with patch.object(workflow_store, '_get_workflows_path', lambda: blank):
            decision = self.choose('계측 원시값 31, 영점 7, gain 3에 대해 (원시값-영점)*gain으로 보정하라. '
                                   '등록 부품 없음. 출력 {"code":"IBL 프로그램"}.')
            output = handle_request({'edition': 2, 'code': decision['code']}, str(self.directory))
            self.results['baseline'] = {'execution': output, 'correct': output.get('value') == 72}

    def steering(self):
        from ibl_v2_adapters import Adapter
        from ibl_v2_entry import handle_request
        from ibl_v2_ir import digest
        from ibl_run_control import status, steer
        from thread_context import actor_context, snapshot, restore
        entered, release = threading.Event(), threading.Event()
        handles, results, effects = [], [], []
        def gate(rt, args):
            handles.append(rt.journal.control['task_ref'])
            entered.set()
            if not release.wait(210):
                raise TimeoutError('gate deadline')
            return 0
        registry = {
            't:gate': Adapter({'version': 1, 'params': {}, 'result': 'Number', 'effects': ['read_external']}, gate),
            't:send': Adapter({'version': 1, 'params': {'n': 'Number'}, 'result': 'Number',
                              'effects': ['write_external'], 'write_resources': {'delivery': 'n'}},
                             lambda rt, a: effects.append(a['n']) or a['n'])}
        code = '[def:scale]($n){return $n*2}; [t:send]{n:41}; [t:gate]{}; return [fn:scale]{n:5}'
        request = {'edition': 2, 'code': code}
        with actor_context(agent_id='repair-acceptance', task_id='steering-acceptance'), \
                patch('ibl_v2_adapters.load_registry', return_value=registry), \
                patch('tool_batch.prepared_plan', return_value=None):
            context = snapshot()
            def execute():
                restore(context)
                results.append(handle_request(request, str(self.directory)))
            worker = threading.Thread(target=execute)
            worker.start()
            try:
                if not entered.wait(15):
                    raise RuntimeError('gate not entered: ' + str(results))
                before = status(handles[0])
                guide = (ROOT / 'data/guides/task_receipts.md').read_text().split(
                    '### 다음 순수 함수 호출의 본문 변경', 1)[1].split('첫 지원 범위', 1)[0]
                decision = self.choose('실행 중 프로그램=' + code + '\n현재 실제 status=' + json.dumps(before) +
                    '\n현재 운영 조향 가이드=' + guide +
                    '\n배율 요구가 2에서 4로 바뀌었다. 완료한 전송은 반복하지 말고 아직 시작하지 않은 '
                    '순수 함수 본문만 수정하라. status에서 좌표를 선택하라. '
                    '출력 {"payload":{"root_task":...,"plan_hash":...,"node_id":...,"revision":...,'
                    '"ordinal":...,"definition":"새 본문"},"expected_args":{...}}. '
                    'scope가 있는 경계면 payload에 scope를 그대로 포함. expected_args는 네가 추론한 전체 입력; '
                    'harness가 운영 digest(expected_args)를 계산해 expected_args_hash에 넣는다.')
                payload = {**decision['payload'], 'expected_args_hash': digest(decision['expected_args'])}
                accepted = steer(handles[0], payload, 'model-decision')
                release.set()
                worker.join(15)
                after = status(handles[0])
                resumed = handle_request({**request, 'resume': {'run_id': handles[0]['task_id']}}, str(self.directory))
                self.results['steering'] = {'before': before, 'decision': decision, 'accepted': accepted,
                    'after': after, 'execution': results, 'resumed': resumed, 'effects': effects,
                    'correct': bool(results and results[0].get('value') == 20 and
                                    resumed.get('value') == 20 and effects == [41])}
            finally:
                release.set()
                worker.join(15)

    def recovery(self):
        import consciousness_agent as ca
        from conscious_supervisor import Supervisor
        from final_evaluator import prepare
        from evaluation_input import record
        from thread_context import actor_context
        for bad in (False, True):
            name = 'contradiction' if bad else 'completion'
            directory = self.directory / name
            with actor_context(agent_id='repair-acceptance', task_id=name), patch.object(ca, 'call_oneshot_provider', self.call):
                ai = SimpleNamespace(agent_id='repair-acceptance', project_path=str(directory), tools=[],
                                     _custom_execute_tool=lambda *a, **kw: None)
                controller = Supervisor(SimpleNamespace(ai=ai), '최종 확정 원장 합계를 보고하라.', [],
                    'repair-acceptance', name, {'tick_s': 1000, 'max_repairs': 0}, directory=directory)
                controller.configure({'task_framing': '원장 합계 대조',
                                      'achievement_criteria': '제출한 합계가 최종 확정 원장의 세 금액 합과 일치한다.'})
                response = '확정 원장의 합계는 270원입니다.'
                controller.store.put_response(response)
                packet = prepare(controller)
                prefix = '이전 기간의 설명이며 최종 원장은 마지막 구간에 있다.\n' + '이전 업무 메모.\n' * 2000
                body = prefix + '최종 확정 원장: A=120원, B=80원, C=' + ('60' if bad else '70') + '원. 확정 건은 세 건뿐이다.'
                ref = controller.store.evidence(body)
                packet['attachments'] = [record(body[:35], subject=f'final_ledger; 최종 원장 Unicode [{len(prefix)},{len(body)})',
                    source_ref=ref['id'], revision=ref['id'], total=len(body))]
                packet['files'] = ''
                controller._resume_evaluation = True
                try:
                    events = list(controller.finalize(response, [], lambda ev: None))
                    logs = [json.loads(line) for line in (directory / 'events.jsonl').read_text().splitlines()]
                    decisions = [r for r in logs if r.get('kind') == 'decision']
                    recovered = [r for r in logs if r.get('kind') == 'evaluation.evidence_recovered']
                    self.results[name] = {'events': events, 'decisions': decisions, 'recovered': recovered,
                                          'expected': 'REWORK' if bad else 'APPROVED'}
                finally:
                    controller.close()
            self.save()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--cases', nargs='+', choices=['reuse', 'steering', 'recovery'],
                        default=['reuse', 'steering', 'recovery'])
    args = parser.parse_args()
    directory = args.output.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    db = isolate(directory)
    # Environment failures are separate from model failures; don't remove standard Python builtins.
    assert type(1) is int and sum([2, 3]) == 5
    from ibl_v2_entry import handle_request
    assert handle_request({'edition': 2, 'code': 'return 2+3'}, str(directory))['value'] == 5
    experiment = Experiment(directory)
    for name, run in [('reuse', lambda: experiment.reuse(db)), ('steering', experiment.steering),
                      ('recovery', experiment.recovery)]:
        if name not in args.cases:
            continue
        print('START', name, flush=True)
        try:
            run()
        except Exception as exc:
            experiment.results[name + '_error'] = type(exc).__name__ + ': ' + str(exc)
        experiment.save()
        print('FINISH', name, flush=True)


if __name__ == '__main__':
    main()
