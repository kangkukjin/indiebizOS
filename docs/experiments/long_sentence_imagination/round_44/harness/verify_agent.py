"""독립 AI 산출물(키 이름이 다름)을 훈련자 모양으로 정규화한 사본을 만들어 verify.py 로 같은 검수를 돌린다.
사용: verify_agent.py <agent_out> <state_json> <oracle> <qa.json> [--flaky]  — 정규화 사본은 <agent_out>_norm/"""
import json, os, shutil, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent

def main():
    out, state, oracle, qa = map(Path, sys.argv[1:5]); flaky = '--flaky' in sys.argv
    norm = out.parent / (out.name + '_norm'); shutil.rmtree(norm, ignore_errors=True); norm.mkdir()
    for p in out.glob('**/*.png'):
        rel = p.relative_to(out); (norm / rel).parent.mkdir(parents=True, exist_ok=True); os.symlink(p.resolve(), norm / rel)
    if (out / 'report.md').exists(): shutil.copy(out / 'report.md', norm / 'report.md')
    d = json.loads((out / 'result.json').read_text())
    g = lambda *ks: next((d[k] for k in ks if k in d), None)
    comp = g('comparison', 'compare') or {}
    ren = g('renewals', 'extensions', 'extension_results') or []
    ext = []
    for r in ren:
        res = r.get('result') or ('success' if r.get('ok') else ('not_requested' if r.get('attempted') is False else 'failed'))
        ext.append({'id': r.get('id'), 'attempted': res != 'not_requested', 'ok': res == 'success', 'reason': r.get('reason') or r.get('fail_reason'),
                    'due_before': r.get('before_due') or r.get('due_before'),
                    'due_after': r.get('new_due') or r.get('due_after') or r.get('after_due') or r.get('due_after_reread') or r.get('new_due_reread')})
    notice = g('notice', 'notice_holiday')
    if isinstance(notice, dict):
        cs = notice.get('closure_sentences') or notice.get('holiday_sentences')
        hs = notice.get('holiday_sentence'); hs = hs[0] if isinstance(hs, list) and hs else hs
        notice = (cs[0] if isinstance(cs, list) and cs else None) or hs or notice.get('holiday') or notice.get('sentence') or notice.get('text') or json.dumps(notice, ensure_ascii=False)
    desk = g('desktop') or {}
    fm = g('frontmost_app') or (desk.get('frontmost_app') if isinstance(desk, dict) else None) or (desk.get('front_app') if isinstance(desk, dict) else None)
    pg = g('page_count', 'pages', 'total_pages')
    if pg is None and isinstance(g('completeness'), dict):
        c = g('completeness'); pr = c.get('pages_read'); pg = c.get('pages_total') or c.get('page_count') or c.get('pages_header') or c.get('pages') or (len(pr) if isinstance(pr, list) else pr)
    if isinstance(pg, list): pg = len(pg)
    if isinstance(pg, dict): pg = pg.get('count') or pg.get('total') or len(pg.get('items', []))
    n = {'today': g('base_date', 'today'), 'pages': pg,
         'loans': g('loans', 'rows') or [], 'compare': {'portal_only': comp.get('portal_only'), 'mine_only': comp.get('mine_only'),
         'due_mismatch': comp.get('due_differs') or comp.get('due_mismatch')}, 'urgent': [r.get('id') for r in ren], 'extensions': ext,
         'notice_holiday': notice, 'frontmost_app': fm, '_normalized_from': list(d.keys())}
    (norm / 'result.json').write_text(json.dumps(n, ensure_ascii=False, indent=1))
    cmd = [sys.executable, str(HERE / 'verify.py'), str(norm), str(state), str(oracle), str(qa)] + (['--flaky'] if flaky else [])
    subprocess.run(cmd, check=True)

if __name__ == '__main__':
    main()
