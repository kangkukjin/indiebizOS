#!/usr/bin/env python3
"""Compare full/selected evidence with one configured evaluator; no research or tool execution.

Live calls require --live. Inputs are deterministic fictional records, not private
research. Each arm may recover existing evidence once, using the production validator.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401

import argparse
import copy
import hashlib
import json
import tempfile
import time
from datetime import date
from types import SimpleNamespace

from evaluation_input import EvaluationPrompt, record, evidence_requests, recover
from supervision_store import TurnStore


def fixture(store, *, incorrect=False):
    criteria = {'criteria': [{'id': 'C1', 'text': '확정 주문 수가 최신 원장과 일치한다.'},
                             {'id': 'C2', 'text': '순매출 합계가 최신 원장의 확정 주문 금액 합과 일치한다.'}]}
    required = ('사용자 요청: 확정 주문 수와 순매출 합계를 보고하고 두 기준을 검수하세요.\n'
                'criteria_contract=' + json.dumps(criteria, ensure_ascii=False) + '\n'
                '제출 보고서: 이번 기간 확정 주문은 3건이고 순매출 합계는 270원입니다.\n'
                '각 자료의 날짜·상태를 구별하세요. 생략된 자료의 부재를 결함으로 단정하지 마세요.\n')
    rows = []
    for i in range(12):
        filler = (f'보관 자료 {i}: 지난 기간의 내부 메모이며 이번 기간의 확정 집계에는 포함하지 않는다.\n' * 80)
        text = filler
        if i == 5:
            amount = 60 if incorrect else 70
            text = (filler[:len(filler)//2] + '\n최신 확정 원장. C1 C2 확정 주문과 순매출:\n'
                    f'A=120원, B=80원, C={amount}원. 확정 주문은 이 세 건이다.\n'
                    '취소 주문 Z=900원은 집계에서 제외한다. 이 원장이 위 보관 메모보다 최신이다.\n' + filler[len(filler)//2:])
        ref = store.evidence(text)
        rows.append(record(text, subject=f'fixture-document-{i}', source_ref=ref['id'], revision=ref['id']))
    return required, rows, criteria


def run_arm(provider, store, required, rows, criteria, *, budget_chars=None):
    from consciousness_agent import call_oneshot_provider, oneshot_failure_details
    from cognitive_eval import CognitiveEvalMixin, parse_eval_verdict
    from final_evaluator import POLICY
    selected = copy.copy(provider)
    selected.request_limits = dict(getattr(provider, 'request_limits', {}) or {})
    if budget_chars is not None:
        selected.request_limits.update(chars=min(budget_chars, selected.request_limits.get('chars', budget_chars)),
                                       source='controlled experiment selection cap; same provider/model')
    system = CognitiveEvalMixin()._load_evaluator_prompt() + '\n\n' + POLICY
    packet = {'attachments': list(rows), 'context': {'criteria_contract': criteria}}
    rounds = []
    started = time.monotonic()
    for attempt in range(2):
        prompt = EvaluationPrompt(required, packet['attachments'], json.dumps(criteria, ensure_ascii=False))
        usage = {}
        request_start = time.monotonic()
        answer = call_oneshot_provider(selected, prompt, system_prompt=system, role='evaluate', usage_sink=usage)
        failure = oneshot_failure_details()
        verdict = parse_eval_verdict(answer or '')[0] if not failure else None
        status = 'ACHIEVED' if verdict is True else 'NOT_ACHIEVED' if verdict is False else 'UNKNOWN'
        rounds.append({'status': status, 'response': answer, 'failure': failure, 'usage': usage,
                       'elapsed_s': round(time.monotonic() - request_start, 6), 'input': prompt.metrics})
        if status != 'UNKNOWN' or failure or attempt:
            break
        requests = evidence_requests(answer or '', packet)
        if not requests:
            break
        recovery_start = time.monotonic()
        recovered = recover(SimpleNamespace(store=store, cancelled=lambda: False), requests)
        packet['attachments'].extend(recovered)
        rounds[-1]['recovery'] = {'requests': requests, 'elapsed_s': round(time.monotonic() - recovery_start, 6)}
    measured = all(r['usage'].get('total_requests') for r in rounds)
    tokens = {key: sum(r['usage'].get(key, 0) for r in rounds) if measured else None
              for key in ('total_input_tokens', 'total_output_tokens', 'total_cache_read_tokens')}
    return {'status': rounds[-1]['status'], 'elapsed_s': round(time.monotonic() - started, 6),
            'tokens': tokens, 'rounds': rounds, 'measured': measured}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--budget-chars', type=int, default=28000)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.live:
        parser.error('This measurement invokes the configured evaluator. Pass --live explicitly.')
    from consciousness_agent import _resolve_oneshot_provider
    provider = _resolve_oneshot_provider('evaluate')
    if provider is None or not provider.is_ready:
        raise RuntimeError('Configured evaluator is unavailable; no model substitution performed')
    report = {'schema': 1, 'date': date.today().isoformat(), 'provider': type(provider).__name__, 'model': provider.model,
              'budget_chars': args.budget_chars, 'fixture': 'fictional order ledger; no user records',
              'tool_calls_authorized': 0, 'cases': [],
              'limitations': ['One sample per case and arm; order/cache/load affect latency.',
                              'Controlled selection cap, not an observed production transport limit.',
                              'Full evidence and budgeted evidence use the same current renderer and evaluator policy.',
                              'No claim about all research tasks or episode 5766 content quality.']}
    def save():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    with tempfile.TemporaryDirectory(prefix='evaluation-budget-fixture-') as directory:
        for incorrect in (False, True):
            store = TurnStore(Path(directory) / str(incorrect))
            required, rows, criteria = fixture(store, incorrect=incorrect)
            case = {'case': 'incorrect_total' if incorrect else 'correct_total',
                    'expected': 'NOT_ACHIEVED' if incorrect else 'ACHIEVED',
                    'input_hash': hashlib.sha256((required + json.dumps(rows, ensure_ascii=False)).encode()).hexdigest(),
                    'original_chars': sum(len(r['text']) for r in rows), 'arms': {}}
            report['cases'].append(case)
            for arm, limit in (('full_evidence', None), ('budgeted_evidence', args.budget_chars)):
                print(f"Starting {case['case']} / {arm}", flush=True)
                case['arms'][arm] = run_arm(provider, store, required, rows, criteria, budget_chars=limit)
                save()
                print(f"Finished: {case['arms'][arm]['status']}", flush=True)
    report['expected_verdicts_match'] = all(a['status'] == c['expected'] for c in report['cases'] for a in c['arms'].values())
    save()


if __name__ == '__main__':
    main()
