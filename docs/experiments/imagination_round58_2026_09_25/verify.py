"""Verify every checked task and every actually executed task, including values."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPECTED = {
    'T01': [{'category': '식비', 'total': 50}, {'category': '교통', 'total': 10}],
    'T02': [{'url': 'a'}, {'url': 'b'}],
    'T04': [{'title': 'A', 'lecture': '기초'}, {'title': 'B', 'lecture': '기초'}],
    'T05': '가나',
    'T07': [{'id': 'c', 'price': 1}, {'id': 'b', 'price': 2}, {'id': 'a', 'price': 3}],
    'T08': [{'id': 'a', 'weighted': 6}],
    'T09': [{'id': 'b', 'price': 200}, {'id': 'c', 'price': 100}],
    'T10': [{'id': 'a', 'ok': True, 'value': 50}, {'id': 'b', 'ok': False, 'error': 'VALUE'}],
    'T11': [{'name': '기초', 'refs': []}, {'name': '심화', 'refs': ['A']}],
    'T12': 5, 'T17': [], 'T19': [],
    'T20': [{'video': 'a', 'n': 1}, {'video': 'a', 'n': 2}, {'video': 'b', 'n': 3}],
    'T21': 'b', 'T22': [{'id': 'a', 'memo': '미검토'}, {'id': 'b', 'memo': '관심'}],
    'T23': [5, 15], 'T24': '검토',
}


def main():
    rows = json.loads((HERE / 'after.json').read_text())
    checks, runs = [], []
    for row in rows:
        result, name = row['response'], row['name']
        assert row['request']['origin'] == 'training'
        if row['request']['check']:
            assert result['status'] in {'valid', 'incomplete'}, row
            assert not result['issues'], row
            checks.append(name)
            continue
        assert result['success'] is True and result['executed'] is True, row
        assert result['source_complete'] is (name != 'T10'), row
        val = result['value']
        if name in EXPECTED:
            assert val == EXPECTED[name], (name, val, EXPECTED[name])
        elif name == 'T03':
            assert val['items'] == [{'id': '가', 'price': 300, 'memo': '관심'}], val
        elif name == 'T06':
            assert val.endswith(' 강의 자료') and len(val.split()[0]) == 4, val
        elif name == 'T18':
            assert len(val) == 1 and val[0]['name'] == 'report.md', val
        else:
            raise AssertionError(f'Missing oracle: {name}')
        runs.append(name)
    assert len(checks) == len(set(checks)) == 24
    assert len(runs) == len(set(runs)) == 20
    out = {'checks': len(checks), 'executions': len(runs), 'values_verified': len(runs),
           'expected_partial': ['T10'], 'all_passed': True}
    (HERE / 'verification.json').write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
