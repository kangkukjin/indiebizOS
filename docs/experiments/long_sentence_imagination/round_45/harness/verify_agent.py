"""독립 AI 산출물(키 이름이 다름)을 훈련자 모양으로 정규화해 verify.py 를 돌린다. 사용: verify_agent.py <agent_out> <state> <oracle> <qa> [--flaky]"""
import json, os, shutil, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent

def g(d, *ks, default=None):
    for k in ks:
        if isinstance(d, dict) and k in d: return d[k]
    return default

def main():
    out, state, oracle, qa = map(Path, sys.argv[1:5]); flaky = '--flaky' in sys.argv
    norm = out.parent / (out.name + '_norm'); shutil.rmtree(norm, ignore_errors=True); norm.mkdir()
    for p in out.glob('**/*.pdf'):
        rel = p.relative_to(out); (norm / rel).parent.mkdir(parents=True, exist_ok=True); os.symlink(p.resolve(), norm / rel)
    if (out / 'report.md').exists(): shutil.copy(out / 'report.md', norm / 'report.md')
    d = json.loads((out / 'result.json').read_text())
    apps = g(d, 'applicants', 'applications', 'results', default=[])
    results, pre = [], []
    for a in apps:
        res = str(g(a, 'result', 'status', default=''))
        ok = g(a, 'ok'); ok = ok if isinstance(ok, bool) else (('접수 완료' in res) or res in ('success', 'ok', '성공'))
        fee = g(a, 'fee_won', 'fee')
        if isinstance(fee, str): fee = int(fee.replace(',', '').replace('원', '') or 0)
        lc = g(a, 'list_check', 'precheck', default={})
        lfee = g(lc, 'fee') if isinstance(lc, dict) else None
        if isinstance(lfee, str): lfee = int(lfee.replace(',', '').replace('원', '') or 0)
        pre.append({'name': a.get('name'), 'fee': lfee if lfee is not None else fee})
        results.append({'name': a.get('name'), 'ok': ok, 'receipt_id': g(a, 'receipt_no', 'receipt_id', 'receipt'), 'reason': g(a, 'reason', 'error'),
                        'fee': fee if ok else None, 'retried': (lambda at: (len(at) if isinstance(at, list) else (at or 1)) >= 2)(g(a, 'attempts', default=1)) or g(a, 'retried') is True})
    sess = g(d, 'session', default={})
    calc = g(d, 'calculator_check', 'calculator', default={})
    if not isinstance(calc, dict): calc = {'status': calc}
    n = {'results': results, 'precheck': pre, 'fee_total_success': g(d, 'fee_total_won', 'fee_total', 'fee_total_success'),
         'list_snapshot': g(d, 'list_snapshot', default={'note': 'AI 는 자체 Playwright 라 snapshot 상한 해당 없음', 'truncated': True}),
         'session': {'login_owner': g(sess, 'login_owner', 'session_owner', 'driver', 'browser', default=''), 'login_tab': g(sess, 'login_tab', 'tab_id', 'portal_url', default='')},
         'calculator': {'done': g(calc, 'done', default=g(calc, 'status') not in (None, '미실행', 'skipped')), **calc}, '_normalized_from': list(d.keys())}
    (norm / 'result.json').write_text(json.dumps(n, ensure_ascii=False, indent=1))
    subprocess.run([sys.executable, str(HERE / 'verify.py'), str(norm), str(state), str(oracle), str(qa)] + (['--flaky'] if flaky else []), check=True)

if __name__ == '__main__':
    main()
