"""Validate recorded observations independently of the runner's pass flags."""
import json
from pathlib import Path
import sys
from probe import CASES

HERE = Path(__file__).resolve().parent


def verify(phase):
    rows = json.loads((HERE / f'{phase}.json').read_text())
    expected = {name: value for name, _, _, value in CASES}
    wanted = {(name, check) for name, _, _, value in CASES
              for check in ([True] if value is None else [True, False])}
    assert len(rows) == len(wanted) == 44
    assert {(r['name'], r['request']['check']) for r in rows} == wanted
    results = []
    for row in rows:
        name, check = row['name'], row['request']['check']
        result = row['response'].get('result', row['response'])
        try:
            assert row['request']['origin'] == 'training'
            assert row['request']['project_id'] == '컨텐츠'
            if check:
                assert result['status'] in ('valid', 'incomplete') and not result['issues']
                assert result['executed'] is False
            else:
                assert result['executed'] is True and result['success'] is True
                assert result['source_complete'] is (name != 'T09')
                assert result['value'] == expected[name]
            passed = True
        except (AssertionError, KeyError):
            passed = False
        results.append(dict(name=name, check=check, passed=passed))
    summary = dict(phase=phase, observations=len(results), passed=sum(r['passed'] for r in results),
                   failed=sum(not r['passed'] for r in results), results=results)
    (HERE / f'{phase}_verification.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k != 'results'},ensure_ascii=False))
    return summary['failed'] == 0


if __name__ == '__main__':
    raise SystemExit(0 if verify(sys.argv[1]) else 1)
