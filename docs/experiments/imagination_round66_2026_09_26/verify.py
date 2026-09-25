"""Verify all persisted observations independently of runner pass flags."""
import json
from pathlib import Path
import sys
from probe import CASES

HERE = Path(__file__).resolve().parent


def verify(phase):
    rows = json.loads((HERE / f'{phase}.json').read_text())
    cases = {name: (code, mode, expected) for name, _, code, mode, expected in CASES}
    expected_keys = {(name, check) for name, _, _, mode, _ in CASES
                     for check in ([True] if mode == 'check' else [True, False])}
    assert len(rows) == len(expected_keys) == 44
    assert {(r['name'], r['request']['check']) for r in rows} == expected_keys
    observations = []
    for row in rows:
        code, mode, expected = cases[row['name']]
        request = row['request']
        result = row['response'].get('result', row['response'])
        try:
            assert request['code'] == '#!ibl edition=2\n' + code
            assert request['edition'] == 2
            assert request['origin'] == 'training' and request['project_id'] == '컨텐츠'
            if request['check']:
                assert result['executed'] is False and not result['issues']
                assert result['status'] in ('valid', 'incomplete')
            else:
                assert result['executed'] is True
                if mode == 'runtime_error':
                    assert result['success'] is False
                    assert result['diagnostic']['code'] == expected
                    assert result['diagnostic']['kind'] == 'runtime'
                else:
                    assert result['success'] is True and result['value'] == expected
                    assert result['source_complete'] is (mode != 'partial')
                    if mode == 'partial':
                        assert any(e['kind'] == 'collected_error' for e in result['evidence'])
            ok = True
        except AssertionError:
            ok = False
        assert ok == row['passed'], (row['name'], 'runner disagreement')
        observations.append({'name': row['name'], 'check': request['check'], 'passed': ok})
    summary = {'phase': phase, 'passed': sum(r['passed'] for r in observations),
               'total': len(rows), 'observations': observations}
    (HERE / f'{phase}_verification.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    print(f"{phase}: {summary['passed']}/{summary['total']}")
    return summary['passed'] == summary['total']


if __name__ == '__main__':
    raise SystemExit(0 if verify(sys.argv[1]) else 1)
