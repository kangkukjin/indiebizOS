"""Isolated real-model continuation smoke. No production requests or writable tools.

Run from the repository: .venv/bin/python3 docs/experiments/failure_recovery_2026_11_04/live.py
This checks the continuation packet and final answer, not external effect execution.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401
import json
import tempfile
import time
from types import SimpleNamespace

import execution_turn
from providers.codex import CodexProvider
from providers.base import turn_token_scope
from task_continuation import continue_task
from thread_context import actor_context

CASES = [
    {'name': 'aggregation', 'request': '확정 주문 12, 18, 7의 합계와 건수를 JSON {"total":정수,"count":정수}로 답하세요. 취소 주문 90은 제외하세요.',
     'previous': '전용 집계 도구의 열 이름 오류를 확인했습니다.',
     'calls': [{'id': 'sum', 'name': 'aggregate', 'input': {'column': 'amount'},
                'result': {'success': False, 'error': 'column not found', 'available': 'net'}},
               {'id': 'guide', 'name': 'read_guide', 'result': {'success': True, 'guide': 'net is the order amount'}}],
     'expected': {'total': 37, 'count': 3}},
    {'name': 'document', 'request': 'OCR 본문 "항목 A 수량 2 단가 15; 항목 B 수량 3 단가 8"을 행 2개와 합계로 정리하세요. JSON {"rows":[{"item":"A","quantity":2,"price":15,"subtotal":30}, ...],"total":정수}만 답하세요.',
     'previous': '표 변환기 오류를 진단하고 도움말을 읽었습니다.',
     'calls': [{'id': 'convert', 'name': 'table_convert', 'result': {'success': False, 'error': 'unsupported table layout'}},
               {'id': 'help', 'name': 'read_help', 'result': {'success': True, 'guide': 'plain text can be structured directly'}}],
     'expected': {'rows': [{'item': 'A', 'quantity': 2, 'price': 15, 'subtotal': 30},
                           {'item': 'B', 'quantity': 3, 'price': 8, 'subtotal': 24}], 'total': 54}},
    {'name': 'irrelevant_search_failure', 'request': '제공된 확정 값 4와 9의 합을 JSON {"total":정수}로만 답하세요. 외부 자료는 필요 없습니다.',
     'previous': '{"total":13}',
     'calls': [{'id': 'search', 'name': 'shell', 'is_error': True,
                'result': {'exit_code': 1, 'stdout': '', 'stderr': ''}},
               {'id': 'sum', 'name': 'calculate', 'result': {'success': True, 'total': 13}}],
     'expected': {'total': 13}},
]


def drain(stream):
    events = []
    while True:
        try:
            events.append(next(stream))
        except StopIteration as end:
            return events, end.value


def main():
    report = {'schema': 1, 'model': 'gpt-6-astra:high', 'fixture': 'fictional inline data',
              'scope': 'real continuation prompt + model answer; no production task or effect replay', 'cases': []}
    with tempfile.TemporaryDirectory(prefix='failure-recovery-live-') as workspace:
        for case in CASES:
            provider = CodexProvider(api_key='', model=report['model'], tools=[], project_path=workspace,
                agent_id='recovery-live-' + case['name'], agent_name='recovery smoke',
                system_prompt='완결된 입력 자료로 원래 업무의 답을 작성하세요. 도구·파일·네트워크를 사용하지 마세요. JSON만 출력하세요.')
            # This is an isolated read-only model probe, not a second product evaluator.
            provider.agent_role = 'consciousness'
            provider.no_tools = True
            provider.disable_session_persistence = True
            assert provider.init_client()
            invocations = []
            def stream(message_content, **kw):
                invocations.append(message_content)
                yield from provider.process_message_stream(message=message_content, **kw)
            runner = SimpleNamespace(ai=SimpleNamespace(process_message_stream=stream))
            start = time.monotonic()
            with actor_context(agent_id=provider.agent_id, task_id=case['name'], origin='training'), \
                    turn_token_scope(provider.agent_id, case['name'], hard_token_limit=100000, deadline_s=120):
                turn = execution_turn.Binding(runner, provider.agent_id, case['name'], context={}, conversation=None)
                token = execution_turn._current.set(turn)
                try:
                    events, response = drain(continue_task(runner, case['request'], case['previous'], case['calls'], [],
                        collect=lambda event: None, cancel_check=lambda: time.monotonic() - start > 110))
                    drain(continue_task(runner, case['request'], response, case['calls'], [], collect=lambda event: None))
                finally:
                    execution_turn._current.reset(token)
            try:
                answer = json.loads(response)
            except (TypeError, ValueError):
                answer = None
            usage = provider.metrics.to_dict()
            passed = (answer == case['expected'] and len(invocations) == 1
                      and usage['total_requests'] > 0 and not any(e.get('type') == 'error' for e in events))
            row = {**case, 'response': response, 'passed': passed,
                   'model_invocations': len(invocations), 'elapsed_s': round(time.monotonic() - start, 3),
                   'usage': usage,
                   'tool_events': [e for e in events if e.get('type') in {'tool_start', 'tool_result', 'error'}]}
            report['cases'].append(row)
            Path(__file__).with_name('live.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
            print(json.dumps({k: row[k] for k in ('name', 'passed', 'model_invocations', 'elapsed_s')}, ensure_ascii=False), flush=True)
    assert all(row['passed'] for row in report['cases'])


if __name__ == '__main__':
    main()
