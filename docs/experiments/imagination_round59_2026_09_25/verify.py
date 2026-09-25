"""Task values, source completeness and deliberate partial results are assertions."""
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
EXPECTED = {
    'T01': [], 'T04': [{'title': 'A', 'title_2': '별칭', 'title_3': '기초'}],
    'T05': [], 'T06': [{'id': 'a', 'kind': '전세', 'price': 50}], 'T07': [{'id': 'b'}],
    'T08': [{'day': '월', 'method': '카드', 'n': 2}, {'day': '화', 'method': '현금', 'n': 1}],
    'T09': [{'author': '홍길동', 'title': '자료명'}], 'T10': [],
    'T12': [{'title': '오류 연구', 'error': '개념명', 'truncated': True}],
    'T13': 260, 'T14': [{'weighted': 10}], 'T15': 10,
    'T16': [[{'n': 2, 'score': 6}], [{'n': 4, 'score': 20}]],
    'T17': [{'id': 'a', 'value': 50}, {'id': 'b', 'value': '확인 필요'}],
    'T18': 6, 'T19': 10, 'T20': True,
}
PARTIAL = {'T02': [{'title': 'A', 'lecture': '기초'}],
           'T03': [{'title': 'A', 'lecture': '기초'}], 'T11': [{'title': 'A'}]}


def verify(phase):
    results = []
    evidence = json.loads((HERE / f'{phase}.json').read_text())
    assert len(evidence) == 44
    for row in evidence:
        name, check = row['name'], row['request']['check']
        r = row['response'].get('result', row['response'])
        try:
            if check:
                assert r['status'] in ('valid', 'incomplete') and not r['issues']
            else:
                assert r['executed'] is True
                if name in PARTIAL:
                    assert r['success'] is False and r['source_complete'] is False
                    assert r['diagnostic']['code'] == 'PARTIAL_SOURCE'
                    assert r['diagnostic']['partial']['items'] == PARTIAL[name]
                    if name == 'T02':
                        assert r['diagnostic']['partial']['skipped_row_indices'] == [1]
                    else:
                        assert r['diagnostic']['partial']['row_honesty'][0]['row_index'] == 0
                else:
                    assert r['success'] is True and r['value'] == EXPECTED[name]
                    assert r['source_complete'] is (name != 'T17')
            results.append({'name': name, 'check': check, 'passed': True})
        except (AssertionError, KeyError):
            results.append({'name': name, 'check': check, 'passed': False})
    summary = {'phase': phase, 'passed': sum(r['passed'] for r in results),
               'failed': sum(not r['passed'] for r in results), 'results': results}
    (HERE / f'{phase}_verification.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False))
    return not summary['failed']


if __name__ == '__main__':
    raise SystemExit(0 if verify(sys.argv[1] if len(sys.argv) > 1 else 'after') else 1)
