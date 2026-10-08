"""산출물을 oracle 과 대조. 사용: verify.py <who> <mode>  (mode=base|A|B|C)"""
import json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-09_40회차'
EXP = json.load(open(OUT / 'oracle' / 'expected.json'))
OUTDIR = {'base': 'out', 'A': 'outA', 'B': 'outB', 'C': 'outC'}

def num(x):
    try: return round(float(x), 4)
    except Exception: return None

def aging_map(v):
    if isinstance(v, dict): return {k: num(x) for k, x in v.items()}
    out = {}
    for r in v or []:
        if isinstance(r, dict):
            k = r.get('bucket') or r.get('name') or r.get('range'); val = r.get('total', r.get('balance', r.get('amount')))
            out[k] = num(val)
    return out

def pick(d, *names):
    """여러 이름 중 처음 존재하는 키 값. 독립 AI 는 다른 이름을 고른다(34회차 교훈: 검수기가 두 모양을 정규화)."""
    for n in names:
        if isinstance(d, dict) and n in d and d[n] is not None:
            return d[n]
    return None

def find_key(row, *subs):
    for k in (row or {}):
        if any(sub in k.lower() for sub in subs):
            return k
    return None

def norm_rec(r):
    if not r: return None
    rec = r.get('receivables', {}); dep = r.get('deposits', {}); wd = r.get('withdrawals', {}); bk = r.get('bank_checks', {})
    adv = pick(r, 'advances')
    if adv is None and dep.get('prepayments') is not None:
        adv = {p.get('client_id'): p.get('amount') for p in dep['prepayments']}
    bc = pick(r, 'balance_check') or ({'matches_summary': not bk.get('any_mismatch')} if bk else {})
    return {'aging': pick(r, 'aging') or rec.get('aging'), 'open_total': pick(r, 'open_total') or rec.get('total_open'),
            'top_clients': pick(r, 'top_clients') or rec.get('top5_clients') or [], 'unmatched_deposits': pick(r, 'unmatched_deposits') or dep.get('unidentified'),
            'advances': adv or {}, 'unexplained': pick(r, 'unexplained') or wd.get('unmatched') or [], 'balance_check': bc, 'performance': pick(r, 'performance') or {}}

def main():
    who, mode = sys.argv[1], sys.argv[2]
    d = OUT / who / OUTDIR[mode]; checks = []
    exp = EXP['A'] if mode == 'A' else EXP['base']
    rec = norm_rec(json.load(open(d / 'reconciliation.json'))) if (d / 'reconciliation.json').exists() else None
    fc = json.load(open(d / 'forecast.json')) if (d / 'forecast.json').exists() else None
    ct = json.load(open(d / 'contracts.json')) if (d / 'contracts.json').exists() else None
    memo = (d / 'memo.md').read_text() if (d / 'memo.md').exists() else None
    checks.append(('files exist', all(x is not None for x in (fc, ct, memo)) and (rec is not None or mode == 'B'), [n for n, x in (('rec', rec), ('fc', fc), ('ct', ct), ('memo', memo)) if x is None]))
    if rec and mode != 'B':
        E = exp['reconciliation']
        got = aging_map(rec.get('aging'))
        checks.append(('aging', all(got.get(k) == num(v) for k, v in E['aging'].items() if v), {'got': got, 'exp': E['aging']}))
        checks.append(('open_total', num(rec.get('open_total')) == num(E['open_total']), (rec.get('open_total'), E['open_total'])))
        top = [(r.get('client_id'), num(r.get('balance'))) for r in rec.get('top_clients', [])][:3]
        checks.append(('top3 clients', top == [(r['client_id'], num(r['balance'])) for r in E['top_clients'][:3]], top))
        checks.append(('unmatched deposits', len(rec.get('unmatched_deposits') or []) == len(E['unmatched_deposits']), rec.get('unmatched_deposits')))
        adv = rec.get('advances') or {}
        adv = {k: num(v) for k, v in (adv.items() if isinstance(adv, dict) else [(a.get('client_id'), a.get('amount', a.get('balance'))) for a in adv])}
        checks.append(('advances', adv == {k: num(v) for k, v in E['advances'].items()}, adv))
        une = rec.get('unexplained') or []
        suppliers = {c['supplier'] for c in exp['contracts']}
        une_core = [u for u in une if u.get('counterparty') not in suppliers]
        checks.append(('unexplained count (계약 공급자 제외)', len(une_core) == len(exp['unexplained']), [(u.get('counterparty'), u.get('amount')) for u in une]))
        bc = rec.get('balance_check') or {}
        checks.append(('balance matches_summary', bc.get('matches_summary') == exp['balance_check']['matches_summary'], bc))
        pf = rec.get('performance') or {}
        if pf:
            checks.append(('performance', num(pf.get('revenue')) == num(exp['performance']['revenue']) and num(pf.get('gross_margin')) == num(exp['performance']['gross_margin']), pf))
        else:
            checks.append(('performance (memo)', memo is not None and f"{exp['performance']['revenue']:,}" in memo and ('35.25' in memo or '0.3525' in memo), 'reconciliation 에 performance 없음 → 메모로 확인'))
    if fc:
        E = EXP['B']['forecast'] if mode == 'B' else exp['forecast']
        rows = (pick(fc, 'forecast', 'months') if isinstance(fc, dict) else fc) or []
        breaking = set(fc.get('months_breaking_min') or []) if isinstance(fc, dict) else set()
        ck = find_key(rows[0] if rows else {}, 'closing', 'ending', 'end_balance') or 'closing'
        bk_ = find_key(rows[0] if rows else {}, 'below', 'break', 'under')
        got = [(r.get('month'), num(r.get(ck)), bool(r.get(bk_)) if bk_ else (r.get('month') in breaking)) for r in rows]
        checks.append(('forecast closings+flags', got == [(r['month'], num(r['closing']), r['below_min']) for r in E], got))
    if ct:
        rows = (pick(ct, 'items', 'contracts') if isinstance(ct, dict) else ct) or []
        got = {r.get('id'): r for r in rows if isinstance(r, dict)}
        E = {c['id']: c for c in exp['contracts']}
        def eff(r): return r.get('effective_fee_sep', r.get(find_key(r, 'effective') or '', None))
        def ren(r): return r.get('renewal_date', r.get('expiry', r.get(find_key(r, 'renewal', 'expir') or '', None)))
        def act(r): return r.get('action_within_30d', r.get('expires_within_30_days'))
        fields_ok = all(got.get(k) and num(eff(got[k])) == num(c['effective_fee_sep']) and str(ren(got[k])) == c['renewal_date'] and num(got[k].get('notice_days')) == num(c['notice_days']) for k, c in E.items())
        checks.append(('contracts 5 fields (effective fee, renewal_date, notice_days)', fields_ok, {k: (eff(got.get(k, {})), ren(got.get(k, {})), got.get(k, {}).get('notice_days')) for k in E}))
        flags_ok = all(got.get(k) and bool(got[k].get('notice_deadline_passed')) == c['notice_deadline_passed'] and bool(act(got[k])) == c['action_within_30d'] for k, c in E.items())
        checks.append(('contracts flags', flags_ok, {k: (act(got.get(k, {})), got.get(k, {}).get('notice_deadline_passed')) for k in E}))
    if memo:
        req = ['실적', '미수', '출금', '전망', '계약', '지난달', '리스크', '질문']
        checks.append(('memo sections', all(s in memo for s in req), [s for s in req if s not in memo]))
        checks.append(('memo mentions prior decisions', ('C07' in memo or '동해수산' in memo) and ('K04' in memo or '복합기' in memo), ''))
        # 숫자 근거: 메모의 7자리 이상 숫자(금액)가 계산값 집합에 있는가
        allowed = set()
        def collect(o):
            if isinstance(o, dict): [collect(v) for v in o.values()]
            elif isinstance(o, list): [collect(v) for v in o]
            elif isinstance(o, (int, float)) and not isinstance(o, bool): allowed.add(int(o))
        collect(exp); collect(EXP['B'] if mode == 'B' else {}); allowed.update({30000000, 60000000, 70000000})  # targets.json·변형 B 최소 잔고
        sums = {}
        for r in exp['reconciliation']['open_invoices']:
            sums[r['client_id']] = sums.get(r['client_id'], 0) + r['balance']
        allowed.update(sums.values())   # 거래처별 미수 합(메모의 C07 잔액 등)
        nums = [int(n.replace(',', '')) for n in re.findall(r'-?\d[\d,]{6,}', memo)]
        bad = sorted({n for n in nums if n not in allowed and -n not in allowed})
        checks.append(('INFO memo amounts not in oracle set (파생 소계 가능)', True, bad[:8]))
        print('INFO memo numbers outside oracle set:', bad[:8])
        if mode == 'A':
            checks.append(('memo flags source mismatch', ('불일치' in memo or '원천 확인' in memo), ''))
    ok = all(c[1] for c in checks)
    for n, p, dd in checks: print(('PASS' if p else 'FAIL'), n, '' if p else json.dumps(dd, ensure_ascii=False, default=str)[:500])
    print('RESULT', who, mode, 'ALL PASS' if ok else 'FAILED')
    (OUT / 'runs' / f'verify_{who}_{mode}.json').write_text(json.dumps({'checks': [(n, p, str(dd)[:400]) for n, p, dd in checks], 'ok': ok}, ensure_ascii=False, indent=1))

if __name__ == '__main__':
    main()
