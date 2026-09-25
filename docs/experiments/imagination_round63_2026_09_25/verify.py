"""Check persisted API observations without trusting runner flags."""
import json
from pathlib import Path
import sys
from probe import CASES

HERE = Path(__file__).resolve().parent


def verify(phase):
    observations = json.loads((HERE / f'{phase}.json').read_text())
    cases = {name: (code, mode, value) for name, _, code, mode, value in CASES}
    wanted = {(name, check) for name, _, _, mode, _ in CASES
              for check in ([True] if mode == 'check' else [True, False])}
    assert len(observations) == len(wanted) == 44
    assert {(r['name'], r['request']['check']) for r in observations} == wanted
    findings = []
    for row in observations:
        name = row['name']
        code, mode, expected = cases[name]
        req = row['request']; check = req['check']
        result = row['response'].get('result', row['response'])
        try:
            assert req['code'] == '#!ibl edition=2\n' + code
            assert req['origin'] == 'training' and req['project_id'] == '컨텐츠'
            if check:
                assert result['executed'] is False
                assert result['status'] in ('valid', 'incomplete') and not result['issues']
            else:
                assert result['executed'] is True
                if mode == 'error':
                    assert result['success'] is False and result['diagnostic']['code'] == 'TOOL'
                    assert '객체' in result['diagnostic']['message']
                else:
                    assert result['success'] is True and result['value'] == expected
                    assert result['source_complete'] is (mode != 'partial')
            passed = True
        except (AssertionError, KeyError):
            passed = False
        findings.append(dict(name=name, check=check, passed=passed))
    report = dict(phase=phase, observations=len(findings), passed=sum(r['passed'] for r in findings),
                  failed=sum(not r['passed'] for r in findings), results=findings)
    (HERE/f'{phase}_verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print({k:v for k,v in report.items() if k != 'results'})
    return report['failed'] == 0


if __name__ == '__main__':
    raise SystemExit(0 if verify(sys.argv[1]) else 1)
