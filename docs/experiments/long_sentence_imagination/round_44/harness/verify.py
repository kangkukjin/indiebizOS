"""44회차 결정론 검수 — 산출물(result.json·report.md·PNG)과 서버 상태(state.json)를 _oracle 과 대조.
사용: verify.py <out_dir> <state_json> <oracle_dir> <qa.json> [--flaky]"""
import json, sys
from pathlib import Path

def png_ok(p: Path):
    try:
        from PIL import Image
        with Image.open(p) as im: return {"exists": True, "size": list(im.size), "bytes": p.stat().st_size}
    except Exception as e:
        return {"exists": p.exists(), "error": str(e)}

def pick(d, *names, default=None):
    """AI 산출물의 키 이름이 다를 수 있어 후보 키를 순서대로 찾는다."""
    for n in names:
        if isinstance(d, dict) and n in d: return d[n]
    return default

def main():
    out, state_p, oracle, qa_p = map(Path, sys.argv[1:5]); flaky = '--flaky' in sys.argv
    exp = json.loads((oracle / 'expected.json').read_text()); state = json.loads(state_p.read_text())
    checks, detail = {}, {}
    res_p = out / 'result.json'
    checks['result_json_exists'] = res_p.exists(); checks['report_md_exists'] = (out / 'report.md').exists()
    res = json.loads(res_p.read_text()) if res_p.exists() else {}
    if isinstance(res, dict) and 'items' in res and isinstance(res['items'], dict): res = res['items']
    loans = pick(res, 'loans', 'portal_loans', 'all_loans', default=[])
    if isinstance(loans, dict): loans = loans.get('items', [])
    ids = sorted({str(pick(r, 'id', '번호')) for r in loans if isinstance(r, dict)})
    detail['loan_ids'] = ids
    checks['loans_12'] = len(ids) == exp['portal_count']
    checks['pages_3'] = pick(res, 'pages', 'page_count') == exp['pages']
    checks['today'] = str(pick(res, 'today', 'base_date', 'reference_date', default='')).replace('.', '-') == exp['today']
    comp = pick(res, 'compare', 'comparison', 'diff', default=res)
    po = pick(comp, 'portal_only', default=[]); mo = pick(comp, 'mine_only', 'my_only', default=[])
    norm = lambda xs: sorted(str(x.get('id') if isinstance(x, dict) else x) for x in (xs or []))
    checks['portal_only_L08'] = norm(po) == exp['portal_only']; checks['mine_only_L99'] = norm(mo) == exp['mine_only']
    mm = pick(comp, 'due_mismatch', 'mismatch', 'due_diff', default=[])
    checks['due_mismatch_L05_L11'] = norm(mm) == sorted(m['id'] for m in exp['due_mismatch'])
    detail['due_mismatch'] = mm
    urgent = pick(res, 'urgent', 'due_soon', default=[])
    checks['urgent_4'] = norm(urgent) == exp['urgent']
    ext = pick(res, 'extensions', 'extension_results', 'renewals', default=[])
    if isinstance(ext, dict): ext = list(ext.values()) if not 'items' in ext else ext['items']
    ok_ids = sorted(str(e.get('id')) for e in ext if isinstance(e, dict) and e.get('ok') is True)
    skip = [e for e in ext if isinstance(e, dict) and str(e.get('id')) == 'L02']
    exp_ok = exp['flaky']['extend_ok'] if flaky else exp['extend_ok']
    checks['extend_ok_ids'] = ok_ids == exp_ok
    checks['L02_not_attempted'] = bool(skip) and skip[0].get('attempted') is False and skip[0].get('ok') is False
    detail['extensions'] = [{k: e.get(k) for k in ('id', 'attempted', 'ok', 'reason', 'due_before', 'due_after')} for e in ext if isinstance(e, dict)]
    # 새 반납일 재독
    new_due = {str(e.get('id')): str(e.get('due_after') or '').replace('.', '-') for e in ext if isinstance(e, dict) and e.get('ok')}
    checks['new_due_reread'] = all(new_due.get(i) == exp['new_due'][i] for i in exp_ok)
    if flaky:
        fail = [e for e in ext if isinstance(e, dict) and str(e.get('id')) == 'L03']
        checks['L03_failed_with_reason'] = bool(fail) and fail[0].get('ok') is False and '연장 횟수 초과' in str(fail[0].get('reason'))
        checks['page2_retried'] = state.get('page2_hits', 0) >= 2
    # 서버 상태 대조 (진짜 외부 효과)
    checks['server_extended'] = sorted(state['extended']) == exp_ok
    checks['server_no_L02_attempt'] = not any(a['id'] == 'L02' for a in state['attempts'])
    checks['server_attempt_counts'] = len(state['attempts']) == (len(exp_ok) + (1 if flaky else 0))
    detail['server_state'] = state
    # 캡처
    shots = {}
    for i in exp_ok + (['L03'] if flaky else []):
        for k in ('before', 'after'):
            cands = list(out.glob(f'**/*{i}*{k}*.png')) + list(out.glob(f'**/*{k}*{i}*.png'))
            shots[f'{i}_{k}'] = png_ok(cands[0]) if cands else {"exists": False}
    checks['shots_before_after'] = all(v.get('exists') and 'size' in v for k, v in shots.items() if not k.startswith('L03_') or not flaky)
    detail['shots'] = shots
    desk = list(out.glob('**/desktop*.png'))
    detail['desktop'] = png_ok(desk[0]) if desk else {"exists": False}
    checks['desktop_png'] = bool(desk) and 'size' in detail['desktop']
    checks['frontmost_app'] = bool(str(pick(res, 'frontmost_app', 'front_app', default='')).strip())
    notice = str(pick(res, 'notice_holiday', 'notice', 'holiday_notice', default=''))
    checks['notice_exact'] = exp['notice'] in notice and notice.strip().endswith('닫습니다.')
    rep = (out / 'report.md').read_text() if checks['report_md_exists'] else ''
    checks['report_mentions_all'] = all(s in rep for s in ['L08', 'L99', 'L05', 'L11', 'L02'] + exp_ok) and exp['notice'][:12] in rep
    if flaky: checks['report_mentions_L03_fail'] = 'L03' in rep and '연장 횟수 초과' in rep
    passed = sum(1 for v in checks.values() if v); total = len(checks)
    qa = {"passed": passed, "total": total, "checks": checks, "detail": detail}
    qa_p.write_text(json.dumps(qa, ensure_ascii=False, indent=1))
    print(json.dumps({"passed": passed, "total": total, "failed": [k for k, v in checks.items() if not v]}, ensure_ascii=False))

if __name__ == '__main__':
    main()
