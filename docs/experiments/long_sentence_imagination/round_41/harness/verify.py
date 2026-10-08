"""산출물을 oracle 과 대조. 사용: verify.py <who> <mode>  (mode=base|v1|v2|v3)"""
import json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-09_41회차'
EXP = json.load(open(OUT / 'oracle' / 'expected.json'))
OUTDIR = {'base': 'out', 'v1': 'out1', 'v1b': 'out1b', 'v2': 'out2', 'v3': 'out3'}

def num(x, nd=3):
    try: return round(float(x), nd)
    except Exception: return None

def pick(d, *names):
    for n in names:
        if isinstance(d, dict) and d.get(n) is not None: return d[n]
    return None

def find_key(row, *subs):
    for k in (row or {}):
        if any(s in k.lower() for s in subs): return k
    return None

def cond_map(rows):
    out = {}
    if isinstance(rows, dict):
        for k, v in rows.items():
            out[k.replace('_', '-')] = v
        return out
    for r in rows or []:
        if isinstance(r, dict):
            g = r.get('group') or r.get('interface'); t = r.get('task') or r.get('task_type')
            key = r.get('condition') or r.get('key') or (f"{g}-{t}" if g and t else None)
            if key: out[str(key).replace('_', '-')] = r
    return out

def verdict_class(v):
    v = str(v or '')
    if '검정 불가' in v or '불가' in v: return 'untestable'
    if v.startswith('지지') or v == '지지' or v == 'supported' or ('지지' in v and '불' not in v): return 'supported'
    if '반대' in v or 'opposite' in v: return 'opposite'
    if '불지지' in v or '비유의' in v or 'not' in v.lower(): return 'nonsig'
    return v

def main():
    who, mode = sys.argv[1], sys.argv[2]
    d = OUT / who / OUTDIR[mode]; E = EXP['v1' if mode == 'v1b' else mode]; checks = []
    q = json.load(open(d / 'quality.json')) if (d / 'quality.json').exists() else None
    st = json.load(open(d / 'stats.json')) if (d / 'stats.json').exists() else None
    rep = (d / 'report.md').read_text() if (d / 'report.md').exists() else None
    mf = json.load(open(d / 'manifest.json')) if (d / 'manifest.json').exists() else None
    pngs = sorted(p.name for p in d.glob('*.png'))
    checks.append(('files exist', all(x is not None for x in (q, st, rep, mf)), [n for n, x in (('quality', q), ('stats', st), ('report', rep), ('manifest', mf)) if x is None]))
    if q:
        checks.append(('excluded_count', num(pick(q, 'excluded_count', 'excluded_total') or len(pick(q, 'excluded') or [])) == E['quality']['excluded_count'], (pick(q, 'excluded_count'), E['quality']['excluded_count'])))
        checks.append(('duplicate_count', num(pick(q, 'duplicate_count', 'duplicates') or 0) == E['quality']['duplicate_count'], pick(q, 'duplicate_count')))
        checks.append(('low_n_conditions', sorted(str(x).replace('_', '-') for x in (pick(q, 'low_n_conditions', 'low_n', 'conditions_below_min_n') or [])) == E['quality']['low_n_conditions'], pick(q, 'low_n_conditions')))
        sm = pick(q, 'survey_missing', 'missing_survey', 'survey_missing_participants') or []
        sm = [x.get('participant', x.get('id')) if isinstance(x, dict) else x for x in sm]
        checks.append(('survey_missing', sorted(sm) == E['quality']['survey_missing'], sm))
    if st:
        cm = cond_map(pick(st, 'conditions', 'condition_stats'))
        ok = True; detail = {}
        for k, c in E['conditions'].items():
            g = cm.get(k, {})
            mk = find_key(g, 'mean') if g else None
            got = (num(g.get('n')), num(g.get('mean', g.get(mk or '')) if g else None), num(g.get('ci_low', g.get('ci_lower', g.get(find_key(g, 'low') or ''))), 2) if g else None)
            exp = (c['n'], num(c['mean']), num(c['ci_low'], 2))   # CI 는 반올림 경계(…1595) 때문에 2자리
            detail[k] = (got, exp); ok = ok and got == exp
        checks.append(('conditions n/mean/ci_low (6)', ok, {k: v for k, v in detail.items() if v[0] != v[1]}))
        sat = pick(st, 'satisfaction') or {}
        if isinstance(sat, dict) and isinstance(sat.get('by_group'), (list, dict)): sat = sat['by_group']
        if isinstance(sat, list):   # 독립 AI 는 [{group,n,mean}] 모양
            sat = {str(r.get('group') or r.get('interface')): r for r in sat if isinstance(r, dict)}
        got_sat = {g: (num(sat.get(g, {}).get('n')), num(sat.get(g, {}).get('mean'))) for g in ('A', 'B')}
        checks.append(('satisfaction', got_sat == {g: (E['satisfaction'][g]['n'], num(E['satisfaction'][g]['mean'])) for g in ('A', 'B')}, got_sat))
        hs = pick(st, 'hypotheses') or []
        hm = {h.get('id'): h for h in hs if isinstance(h, dict)} if isinstance(hs, list) else hs
        ok = True; detail = {}
        for h in E['hypotheses']:
            g = hm.get(h['id'], {})
            gv = verdict_class(g.get('verdict') or g.get('result') or g.get('conclusion'))
            ev = verdict_class(h['verdict'])
            gt = num(g.get('t'), 2); et = num(h.get('t'), 2) if h.get('t') is not None else None
            detail[h['id']] = ((gv, gt), (ev, et)); ok = ok and gv == ev and (et is None or gt == et)
        checks.append(('hypotheses verdict+t (4)', ok, {k: v for k, v in detail.items() if v[0] != v[1]}))
    fig_paths = [f.get('file') or f.get('path') for f in ((mf or {}).get('figures') or []) if isinstance(f, dict)]
    fig_ok = len(pngs) >= 2 or (mode in ('v1', 'v1b') and len(pngs) >= 1 and all(Path(str(fp)).exists() for fp in fig_paths) and len(fig_paths) >= 2)
    checks.append(('png figures >= 2 (v1 은 이전 그림 참조 허용)', fig_ok and all((d / p).stat().st_size > 0 for p in pngs), (pngs, fig_paths)))
    if rep:
        checks.append(('report references png', any(p in rep for p in pngs) if pngs else False, pngs))
        req = ['초록', '방법', '결과', '한계']
        checks.append(('report sections', all(s in rep for s in req), [s for s in req if s not in rep]))
        claims = [m for m in re.finditer(r'차이가 없다|차이 없음을 입증', rep) if '않' not in rep[m.end():m.end() + 25] and '아니' not in rep[m.end():m.end() + 25]]
        checks.append(('report has no "차이 없음 입증"-style claim', not claims, [rep[m.start() - 30:m.end() + 25] for m in claims][:3]))
        allowed = set()
        def collect(o):
            if isinstance(o, dict): [collect(v) for v in o.values()]
            elif isinstance(o, list): [collect(v) for v in o]
            elif isinstance(o, (int, float)) and not isinstance(o, bool): allowed.update({round(float(o), k) for k in (0, 1, 2, 3, 4)})
        collect({k: v for k, v in E.items() if k != 'input_sha256'})
        nums = [float(n) for n in re.findall(r'(?<![\w.])-?\d+\.\d+(?![\w.])', rep)]
        bad = sorted({n for n in nums if n not in allowed and -n not in allowed and not (0 <= n <= 1)})
        checks.append(('INFO report decimals outside oracle set', True, bad[:10])); print('INFO decimals outside oracle:', bad[:10])
    if mf:
        sh = pick(mf, 'inputs_sha256', 'inputs', 'input_sha256') or {}
        checks.append(('manifest sha256 covers all inputs', len(sh) >= len(E['input_sha256']), (len(sh), len(E['input_sha256']))))
        has_tf = bool(pick(mf, 'tables', 'artifacts')) and (bool(pick(mf, 'figures')) or any('png' in json.dumps(x, ensure_ascii=False) for x in (pick(mf, 'artifacts') or [])))
        checks.append(('manifest has tables and figures', has_tf, list(mf.keys())[:8]))
    if mode in ('v1', 'v1b'):
        cl = (d / 'changelog.md').read_text() if (d / 'changelog.md').exists() else ''
        checks.append(('changelog exists', bool(cl), ''))
        checks.append(('changelog mentions B-T1 and H1, not H4', ('B-T1' in cl or 'B | T1' in cl or 'B-T1' in cl.replace('_', '-')) and 'H1' in cl and 'H4' not in cl.split('그림')[0], cl[:300]))
        checks.append(('fig2 not regenerated', (mf or {}).get('figures') and any((f.get('regenerated') is False) for f in mf['figures']) or 'fig_satisfaction' not in pngs, pngs))
    ok = all(c[1] for c in checks)
    for n, p, dd in checks: print(('PASS' if p else 'FAIL'), n, '' if p else json.dumps(dd, ensure_ascii=False, default=str)[:600])
    print('RESULT', who, mode, 'ALL PASS' if ok else 'FAILED')
    (OUT / 'runs' / f'verify_{who}_{mode}.json').write_text(json.dumps({'checks': [(n, p, str(dd)[:400]) for n, p, dd in checks], 'ok': ok}, ensure_ascii=False, indent=1))

if __name__ == '__main__':
    main()
