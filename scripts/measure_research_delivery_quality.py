#!/usr/bin/env python3
"""Controlled evaluation and read_result execution A/B; fictional data, real model usage."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401

import argparse
import copy
import json
import re
import time
from types import SimpleNamespace

from measure_research_delivery import WORK, write, legacy, call, evaluate, public_result
from evaluation_input import EvaluationPrompt, record, evidence_references
from evaluation_evidence import structured_sections
from supervision_store import TurnStore


def quality_fixture(store, incorrect):
    from research_review import allocate, claims
    facts = ['2026-10-31 확정 표본은 120명이고 투여량은 10 mg이다.',
             '2026-11-01 비교군 연구에서 효과 차이는 0이다. 개선은 입증되지 않았다.',
             '검사 결과: 표 3행 합계는 270원. 코드 검사 L42 FAILED: 분모 0 처리 누락.']
    reports = [facts[0], '관측상 개선 보고도 있지만 비교군에서 개선은 입증되지 않았다.', facts[2]]
    if incorrect:
        reports = ['2026-11-30 확정 표본은 1200명이고 투여량은 10 kg이다.',
                   '비교군에서도 개선이 입증되었다.',
                   '검사 결과: 표 3행 합계는 2700원. 코드 검사 L42 PASSED.']
    if isinstance(incorrect, str):
        reports = [facts[0], '관측상 개선 보고도 있지만 비교군에서 개선은 입증되지 않았다.', facts[2]]
        position, old, new = {
            'number': (0, '120명', '1200명'), 'unit': (0, '10 mg', '10 kg'),
            'date': (0, '2026-10-31', '2026-11-30'),
            'contradiction': (1, '비교군에서 개선은 입증되지 않았다', '비교군에서도 개선이 입증되었다'),
            'code_table': (2, '270원. 코드 검사 L42 FAILED', '2700원. 코드 검사 L42 PASSED'),
        }[incorrect]
        reports[position] = reports[position].replace(old, new)
    source_texts = [('배경 자료: 과거 관측이며 이번 확정값의 근거가 아니다.\n' * 35)
                    + '\n' + facts[i % 3] + '\n해당 날짜·단위·상태에만 적용한다.' for i in range(20)]
    lengths = {str(i): len(t) for i, t in enumerate(source_texts)}
    quotas = allocate(lengths)
    old_citations, receipts, index = [], [], []
    report = '# 가상 임상·코드 연구\n'
    for i, text in enumerate(source_texts):
        marker = f'[자료:fiction-{i}:p1]'
        ref = store.evidence(text)
        index.append({'input': {}, 'result': ref})
        old_citations.append({'citation': marker, 'version_ref': f'fiction-{i}', 'locator': 'p1',
                              'quote': text[:quotas[str(i)]], 'truncated': quotas[str(i)] < len(text),
                              'full_chars': len(text), 'reading_verified': True, 'semantic_status': 'unreviewed',
                              'original_evidence': ref['id'], 'role': 'contradicting' if i % 3 == 1 else 'supporting'})
        receipts.append({**record(text, subject=marker, role='citation', source_ref=ref['id'], revision=ref['id']),
                         'receipt': {'access_id': i, 'version_ref': f'fiction-{i}', 'extraction_revision': 1,
                                     'locator': 'p1', 'role': 'contradicting' if i % 3 == 1 else 'supporting'}})
        report += reports[i % 3] + ' ' + marker + '\n'
    report += '\n미해결: 장기 효과. 현재 자료로 일반화하지 않는다.\n'
    criteria = {'criteria': [{'id': 'C1', 'text': '보고서의 날짜·수량·단위가 읽은 원문과 일치한다.'},
                             {'id': 'C2', 'text': '반대 근거와 조건·미해결을 유지하고 확인되지 않은 효과를 확정하지 않는다.'},
                             {'id': 'C3', 'text': '표 합계와 코드 검사 행·실패 결과를 정확하게 전달한다.'}]}
    from cognitive_eval import CognitiveEvalMixin
    from final_evaluator import POLICY
    required = (CognitiveEvalMixin()._load_evaluator_prompt() + '\n' + POLICY + '\n'
                '사용자: 가상 자료의 연구 보고서를 검수하라. 실제 의료 조언은 아니다.\n달성 기준: '
                + json.dumps(criteria, ensure_ascii=False))
    artifact = store.evidence(report)
    submission = record(report, subject='fixture-report', role='submission', source_ref=artifact['id'], revision=artifact['id'])
    claims_data = claims(report, path='fixture-report', digest='fixed-fixture')
    old_rows = [submission, record(json.dumps(old_citations, ensure_ascii=False), subject='research_citations[0]')]
    old_rows += [record(json.dumps(c, ensure_ascii=False), subject=f'research_claims[{i}]') for i, c in enumerate(claims_data)]
    new_rows = [submission, *receipts, *structured_sections('research_claims', claims_data)]
    for row in [*old_rows, *new_rows]:
        if row['source_ref'] is None:
            ref = store.evidence(row['text'])
            row.update(source_ref=ref['id'], revision=ref['id'], total=ref['chars'])
    context = {'evidence_index': index}
    old_refs = evidence_references({'context': context, 'selection_sources': old_rows})
    old_required = required + '\n원문 회수 주소: ' + json.dumps(old_refs, ensure_ascii=False)
    new_refs = evidence_references({'context': context, 'selection_sources': new_rows})
    return {'required': required, 'old_required': old_required, 'old_rows': old_rows, 'new_rows': new_rows,
            'criteria': criteria, 'references_context': context}, new_refs


def execution_fixture(store):
    from ibl_v2_ir import pack
    import model_result_view as view
    before = legacy('model_result_view')
    view.evidence_store = before.evidence_store = lambda: store
    # The exact-size failure: reading both text/blocks cuts the decisive tail.
    body = ('관측 메모: 과거 값은 최신 확정 집계와 다르다.\n' * 145)
    body += ('자료의 배경과 조건은 위와 같다.\n' * 195)
    body = body[:7600] + '\n확정일=2026-10-31; 수량=120; 단위=mg; 효과=미확인; 코드검사=L42 FAILED; 합계=270원. 끝.'
    value = {'text': body, 'blocks': [{'type': 'paragraph', 'page': 3, 'text': body}]}
    def envelope(v):
        return {'edition': 2, 'success': True, 'source_complete': False, 'value': v,
                'value_wire': {'protocol': 'ibl-value/1', 'data': pack(v)},
                'run_status': 'uncertain', 'diagnostic': {'code': 'UNKNOWN_EFFECT', 'message': '완료 알림 전송 여부 미확인; 재실행 금지'},
                'resume': {'run_id': 'fiction-completed'}, 'evidence': []}
    # The preview helper's warning text also changed. Freeze it for the old arm.
    import model_value_preview
    sys.modules['model_value_preview'] = legacy('model_value_preview')
    try:
        old = before.project_result(envelope(value))
    finally:
        sys.modules['model_value_preview'] = model_value_preview
    new_value = {**value, '_display': {'mirror_fields': [{'field': 'text', 'collection': 'blocks',
                                                        'text_field': 'text', 'separator': ''}]}}
    new = view.project_result(envelope(new_value))
    expected = {'date': '2026-10-31', 'quantity': 120, 'unit': 'mg', 'effect': '미확인',
                'check': 'L42 FAILED', 'total': 270, 'delivery': '미확인', 'repeat_send': False}
    instruction = ('저장 도구 결과에서 확정값과 실패·외부효과 경고를 읽어 결과를 제출하라. '
                   '미리보기가 부족하면 실제 read_result를 요청할 수 있다. 다른 도구/재실행은 없다. '
                   '응답은 JSON 하나: {"read_result":{"id":"실제 id","path":[...],"offset":0,"limit":12000}} '
                   '또는 {"final":{"date":"YYYY-MM-DD","quantity":숫자,"unit":"단위","effect":"확인/미확인",'
                   '"check":"행과 상태","total":숫자,"delivery":"확인/미확인","repeat_send":불리언}}. '
                   '날짜·수량·단위·조건은 추정하지 말라. 완료된 읽기를 새로 실행하지 말라.\n')
    return old, new, expected, instruction


def execute(provider, view, expected, instruction, store):
    import model_result_view
    model_result_view.evidence_store = lambda: store
    prompt = instruction + json.dumps(view, ensure_ascii=False)
    rounds, final, error = [], None, None
    started = time.monotonic()
    for _ in range(4):
        result = call(provider, prompt)
        rounds.append(result)
        try:
            answer = re.sub(r'^```(?:json)?\s*|\s*```$', '', (result['answer'] or '').strip())
            value = json.loads(answer)
            if 'final' in value:
                final = value['final']
                break
            args = value['read_result']
            if args['id'] != view['result_ref']['id']:
                raise ValueError('foreign evidence')
            page = model_result_view.read_result(args)
            prompt += '\n요청: ' + answer + '\nread_result: ' + json.dumps(page, ensure_ascii=False)
        except (ValueError, KeyError, TypeError) as exc:
            error = str(exc)
            break
    return {'rounds': rounds, 'elapsed_s': time.monotonic()-started,
            'status': 'ACHIEVED' if final == expected else 'NOT_ACHIEVED', 'final': final, 'error': error}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', required=True)
    parser.add_argument('--suite', choices=['quality', 'execution'], required=True)
    parser.add_argument('--repetitions', type=int, default=3)
    parser.add_argument('--individual-errors', action='store_true')
    args = parser.parse_args()
    from consciousness_agent import _resolve_oneshot_provider
    provider = _resolve_oneshot_provider('evaluate')
    if provider is None or not provider.is_ready:
        raise RuntimeError('Configured evaluator unavailable')
    provider.no_tools, provider.tools, provider.system_prompt = True, [], ''
    report = {'model': provider.model, 'suite': args.suite, 'cases': [],
              'limits': ['Fictional fixed evidence; does not repeat open-ended research.',
                         'Execution uses model-selected read_result only; no external effects allowed.']}
    suffix = 'individual_errors' if args.individual_errors else args.suite
    output = ROOT / f'docs/experiments/research_delivery_{suffix}_2026_11_04.json'
    cases = (['number', 'unit', 'date', 'contradiction', 'code_table'] if args.individual_errors else
             [False, True] if args.suite == 'quality' else [False])
    for incorrect in cases:
        store = TurnStore(WORK / f'{args.suite}-{incorrect}')
        if args.suite == 'quality':
            frozen, refs = quality_fixture(store, incorrect)
            old_prompt = legacy('evaluation_input').EvaluationPrompt(frozen['old_required'], frozen['old_rows'])
            new_prompt = EvaluationPrompt(frozen['required'], frozen['new_rows'], references=refs)
            inputs = {'old': old_prompt.prepare_request(provider), 'new': new_prompt.prepare_request(provider)}
        else:
            old, new, expected, instruction = execution_fixture(store)
            inputs = {'old': old, 'new': new}
        for repeat in range(args.repetitions):
            for arm in (('old', 'new') if repeat % 2 == 0 else ('new', 'old')):
                print(f'{args.suite} incorrect={incorrect} repeat={repeat} arm={arm}', flush=True)
                result = (evaluate(provider, frozen, store, arm, inputs[arm]) if args.suite == 'quality'
                          else execute(provider, inputs[arm], expected, instruction, store))
                write(WORK / f'{args.suite}-{incorrect}-{repeat}-{arm}.json', result)
                report['cases'].append({'incorrect': incorrect, 'repeat': repeat, 'arm': arm,
                    'expected': 'NOT_ACHIEVED' if incorrect else 'ACHIEVED',
                    'input_chars': len(inputs[arm]) if isinstance(inputs[arm], str) else len(json.dumps(inputs[arm], ensure_ascii=False)),
                    **public_result(result)})
                write(output, report)
                print(json.dumps(report['cases'][-1]), flush=True)


if __name__ == '__main__':
    main()
