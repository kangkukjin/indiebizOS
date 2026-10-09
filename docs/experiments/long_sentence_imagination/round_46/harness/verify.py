"""46회차 결정론 검수 — compare.json·result.json·report.md·hold.pdf 와 서버 A/B state.json 을 _oracle 과 대조.
사용: verify.py <out_dir> <stateA> <stateB> <oracle_dir> <qa.json> [--flaky] [--b]"""
import json, sys
from pathlib import Path
def pick(d, *names, default=None):
    for n in names:
        if isinstance(d, dict) and n in d: return d[n]
    return default
def pdf_text(p):
    for mod in ("pypdf", "PyPDF2"):
        try:
            m = __import__(mod); return "\n".join((pg.extract_text() or "") for pg in m.PdfReader(str(p)).pages)
        except Exception: pass
    try:
        import fitz; return "\n".join(pg.get_text() for pg in fitz.open(str(p)))
    except Exception: pass
    try:
        import pdfplumber
        with pdfplumber.open(str(p)) as d: return "\n".join((pg.extract_text() or "") for pg in d.pages)
    except Exception: pass
    try:
        import subprocess; return subprocess.run(["pdftotext", str(p), "-"], capture_output=True, text=True, timeout=30).stdout
    except Exception as e: return f"<unreadable {e}>"
def main():
    out, sa, sb, oracle, qa = map(Path, sys.argv[1:6]); flaky = '--flaky' in sys.argv; bmode = '--b' in sys.argv
    exp = json.loads((oracle / 'expected.json').read_text()); A = json.loads(sa.read_text()); B = json.loads(sb.read_text())
    checks, detail = {}, {}
    cmp_p = out / 'compare.json'; res_p = out / 'result.json'
    checks['compare_json'] = cmp_p.exists(); checks['result_json'] = res_p.exists(); checks['report_md'] = (out / 'report.md').exists() or (out / 'compare.md').exists()
    cmp = json.loads(cmp_p.read_text()) if cmp_p.exists() else {}; res = json.loads(res_p.read_text()) if res_p.exists() else {}
    rooms = pick(cmp, 'rooms', default=pick(res, 'rooms', default=[]))
    if isinstance(rooms, dict): rooms = rooms.get('items', [])
    totals = {str(pick(r, 'id')): pick(r, 'total') for r in rooms if isinstance(r, dict)}
    exp_tot = {**exp['rooms']['A'], **exp['rooms']['B']}
    checks['six_rooms'] = len(totals) == 6
    checks['totals_match'] = all(totals.get(k) == v for k, v in exp_tot.items() if isinstance(v, int))
    checks['b3_closed'] = any(str(pick(r, 'id')) == 'B3' and (pick(r, 'closed') is True or '마감' in str(pick(r, 'left', 'seats', default=''))) for r in rooms if isinstance(r, dict))
    choice = pick(cmp, 'choice', default=pick(res, 'choice', default={})) or {}
    expc = exp['breakfast_cheapest'] if bmode else exp['cheapest']
    checks['choice'] = str(pick(choice, 'id', 'room')) == expc['room'] and pick(choice, 'total') == expc['total']
    detail['choice'] = choice
    hold = pick(res, 'hold', default={}) or {}
    bh = B['holds']; ah = A['holds']
    if bmode:
        checks['server_hold_B2'] = len(bh) == 1 and bh[0]['room'] == 'B2' and bh[0]['total'] == 236000
    else:
        checks['server_hold_B1'] = len(bh) == 1 and bh[0]['room'] == 'B1' and bh[0]['checkin'] == exp['trip']['checkin'] and bh[0]['nights'] == 2 and bh[0]['guests'] == 2
    checks['server_hold_A_none'] = len(ah) == 0
    checks['consent_essential'] = A['consents'] >= 1 and B['consents'] >= 1
    checks['hold_number_match'] = bool(bh) and str(pick(hold, 'number', 'id', 'hold_number', default='')) == bh[0]['id']
    cc = pick(res, 'compare_check', 'check', default={}) or {}
    verdict = str(pick(res, 'verdict', default=''))
    if flaky:
        checks['server_hold_total_198000'] = bool(bh) and bh[0]['total'] == exp['flaky']['hold_total']
        checks['mismatch_reported'] = pick(cc, 'total_match') is False and ('재결정' in verdict or '다름' in verdict)
    else:
        checks['totals_consistent'] = pick(cc, 'total_match') is True and '일치' in verdict
    pdfs = list(out.glob('**/*.pdf')); txt = pdf_text(pdfs[0]) if pdfs else ''
    checks['pdf_has_hold_number'] = bool(bh) and bh[0]['id'] in txt
    checks['pdf_has_total'] = bool(bh) and f"{bh[0]['total']:,}" in txt
    sess = pick(res, 'session', default={}) or {}
    checks['same_session_two_calls'] = pick(sess, 'same_session') is True or (pick(sess, 'owner') and pick(sess, 'owner') == pick(sess, 'compare_owner'))
    tabs = pick(cmp, 'tabs', default=[]) or []
    checks['two_tabs'] = len(tabs) >= 2
    pv = pick(res, 'preview', default={}) or {}
    checks['preview_reported'] = isinstance(pv, dict) and ('done' in pv or 'status' in pv)
    detail['preview'] = pv; detail['server'] = {'A': {k: A[k] for k in ('logins', 'expired_sessions', 'consents')}, 'B': {k: B[k] for k in ('logins', 'expired_sessions', 'consents')}, 'B_holds': bh, 'A_holds': ah}
    passed = sum(1 for v in checks.values() if v); qa.write_text(json.dumps({"passed": passed, "total": len(checks), "checks": checks, "detail": detail}, ensure_ascii=False, indent=1))
    print(json.dumps({"passed": passed, "total": len(checks), "failed": [k for k, v in checks.items() if not v]}, ensure_ascii=False))
if __name__ == '__main__':
    main()
