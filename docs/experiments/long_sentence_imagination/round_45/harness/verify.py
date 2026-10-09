"""45회차 결정론 검수 — result.json·report.md·PDF 와 서버 state.json 을 _oracle 과 대조.
사용: verify.py <out_dir> <state_json> <oracle_dir> <qa.json> [--flaky] [--only 이름]"""
import json, sys, subprocess
from pathlib import Path

def pick(d, *names, default=None):
    for n in names:
        if isinstance(d, dict) and n in d: return d[n]
    return default

def pdf_text(p: Path):
    try:
        from pypdf import PdfReader
        return "\n".join((pg.extract_text() or "") for pg in PdfReader(str(p)).pages)
    except Exception:
        try:
            return subprocess.run(["pdftotext", str(p), "-"], capture_output=True, text=True, timeout=30).stdout
        except Exception as e:
            return f"<unreadable {e}>"

def main():
    out, state_p, oracle, qa_p = map(Path, sys.argv[1:5]); flaky = '--flaky' in sys.argv
    only = sys.argv[sys.argv.index('--only') + 1] if '--only' in sys.argv else None
    exp = json.loads((oracle / 'expected.json').read_text()); state = json.loads(state_p.read_text())
    apps = [a for a in exp['applicants'] if not only or a['name'] == only]
    exp_ok = [a['name'] for a in apps if not flaky or a['name'] in exp['flaky']['success']]
    exp_fail = [a['name'] for a in apps if flaky and a['name'] not in exp['flaky']['success']]
    checks, detail = {}, {}
    res = json.loads((out / 'result.json').read_text()) if (out / 'result.json').exists() else {}
    checks['result_json'] = bool(res); checks['report_md'] = (out / 'report.md').exists()
    results = pick(res, 'results', 'applications', 'renewals', default=[])
    byname = {str(pick(r, 'name', 'applicant')): r for r in results if isinstance(r, dict)}
    ok_names = sorted(n for n, r in byname.items() if pick(r, 'ok', 'success') is True or pick(r, 'result') == 'success')
    checks['ok_names'] = ok_names == sorted(exp_ok)
    checks['fail_names'] = sorted(n for n, r in byname.items() if n not in ok_names) == sorted(exp_fail)
    # 서버 상태 = 진짜 효과
    sapps = {a['name']: a for a in state['applications']}
    checks['server_applications'] = sorted(sapps) == sorted(exp_ok) if not only else all(n in sapps for n in exp_ok)
    checks['server_course_fee'] = all(sapps[a['name']]['course'] == a['course'] and sapps[a['name']]['fee'] == a['fee'] for a in apps if a['name'] in sapps)
    checks['server_upload_sha'] = all(sapps[a['name']]['upload_sha256'] == a['cert_sha256'] for a in apps if a['name'] in sapps)
    checks['server_code'] = all(sapps[a['name']]['code'] == a['code'] for a in apps if a['name'] in sapps)
    rej = state['rejections']; detail['rejections'] = rej
    if flaky:
        checks['rej_temp_error_once'] = sum(1 for r in rej if '일시 오류' in r['reason']) == 1
        checks['rej_full_once'] = sum(1 for r in rej if '정원 마감' in r['reason']) == 1
        fr = byname.get(exp_fail[0]) if exp_fail else None
        checks['fail_reason_reported'] = bool(fr) and '정원 마감' in str(pick(fr, 'reason', 'error', default=''))
        rr = byname.get(exp_ok[0]) if exp_ok else None
        checks['retry_recorded'] = bool(rr) and (pick(rr, 'retried') is True or pick(rr, 'attempts', default=1) >= 2)
    else:
        checks['no_rejections'] = len(rej) == 0
    # 접수번호·수강료·PDF
    pdf_ok = {}
    for a in apps:
        if a['name'] not in exp_ok: continue
        r = byname.get(a['name'], {}); rid = str(pick(r, 'receipt_id', 'receipt', default=''))
        sid = sapps.get(a['name'], {}).get('id')
        cands = list(out.glob(f'**/*{a["name"]}*.pdf')) + list(out.glob(f'**/*{sid}*.pdf')) if sid else list(out.glob(f'**/*{a["name"]}*.pdf'))
        txt = pdf_text(cands[0]) if cands else ''
        pdf_ok[a['name']] = {"pdf": str(cands[0]) if cands else None, "receipt_id_match": rid == sid, "name": a['name'] in txt, "course": a['course'] in txt,
                             "fee": f"{a['fee']:,}" in txt, "receipt": bool(sid) and sid in txt, "fee_reported": pick(r, 'fee') == a['fee']}
    detail['pdf'] = pdf_ok
    checks['receipt_ids_match'] = all(v['receipt_id_match'] for v in pdf_ok.values())
    checks['pdf_exists_and_matches'] = all(v['pdf'] and v['name'] and v['course'] and v['fee'] and v['receipt'] for v in pdf_ok.values())
    checks['fee_reported'] = all(v['fee_reported'] for v in pdf_ok.values())
    tot = pick(res, 'fee_total_success', 'fee_total', 'total_fee')
    checks['fee_total'] = tot == sum(a['fee'] for a in apps if a['name'] in exp_ok)
    pre = pick(res, 'precheck', 'list_check', default=[])
    checks['precheck_fees'] = all(any(str(pick(p, 'name')) == a['name'] and pick(p, 'fee') == a['fee'] for p in pre) for a in apps) if pre else False
    ls = pick(res, 'list_snapshot', default={})
    checks['snapshot_limit_observed'] = bool(ls) and (pick(ls, 'truncated') is True or (pick(ls, 'shown_count') or 0) < (pick(ls, 'element_count') or 0))
    sess = pick(res, 'session', default={})
    checks['session_fields'] = bool(pick(sess, 'login_owner', 'session_owner', 'owner')) and bool(pick(sess, 'login_tab', 'tab_id', 'tab'))
    calc = pick(res, 'calculator', default={})
    checks['calculator_reported'] = isinstance(calc, dict) and ('done' in calc or 'status' in calc or 'skipped' in calc)
    detail['calculator'] = calc
    rep = (out / 'report.md').read_text() if checks['report_md'] else ''
    checks['report_mentions'] = all(a['name'] in rep for a in apps) and (not flaky or '정원 마감' in rep)
    passed = sum(1 for v in checks.values() if v); qa = {"passed": passed, "total": len(checks), "checks": checks, "detail": detail}
    qa_p.write_text(json.dumps(qa, ensure_ascii=False, indent=1))
    print(json.dumps({"passed": passed, "total": len(checks), "failed": [k for k, v in checks.items() if not v]}, ensure_ascii=False))

if __name__ == '__main__':
    main()
