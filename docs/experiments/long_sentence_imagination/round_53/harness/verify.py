"""53회차 독립 검수 — 사용: verify.py <who> <mode>. 메모·index·summary 를 읽고, 법령 원문은 검수 도구가 따로 가져와(파이썬으로 파싱) 대조한다.
기한 날짜·남은 날은 ±1일 허용(초일 산입 해석 차). 결과는 evidence/<who>_<mode>_qa.json."""
import datetime as dt, json, re, sys, urllib.request
from pathlib import Path
HERE = Path(__file__).resolve().parent.parent
OUT = HERE.parents[3] / 'outputs/long_sentence_imagination/2026-10-11_53회차'
CACHE = OUT / '_oracle' / 'laws.json'

def ibl(code):
    req = urllib.request.Request('http://127.0.0.1:8765/ibl/execute', data=json.dumps({'code': '#!ibl edition=2\n' + code, 'project_id': '수동모드', 'origin': 'training', 'task_id': 'r53-verify'}, ensure_ascii=False).encode(), headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(req, timeout=120)).get('value')

def as_list(v): return v if isinstance(v, list) else [v]

def law_articles(name, cache):
    if name in cache: return cache[name]
    msg = ibl(f'$s = [sense:legal]{{query:{json.dumps(name, ensure_ascii=False)}}}\nreturn $s.message')
    rows = [r for r in as_list(json.loads(msg)['LawSearch'].get('law', [])) if r.get('법령명한글') == name]
    arts = {}
    if rows:
        d = ibl(f'$d = [sense:legal]{{id:"{rows[0]["법령ID"]}"}}\nreturn get(get(get($d,"법령"),"조문"),"조문단위")')
        for j in d:
            if j.get('조문여부') != '조문': continue
            no = f'제{j["조문번호"]}조' + (f'의{j["조문가지번호"]}' if j.get('조문가지번호') else '')
            lines = [j.get('조문내용', '')]
            for h in as_list(j.get('항', [])):
                if isinstance(h, dict):
                    if h.get('항내용'): lines.append(h['항내용'] if isinstance(h['항내용'], str) else json.dumps(h['항내용'], ensure_ascii=False))
                    for o in as_list(h.get('호', [])):
                        if isinstance(o, dict) and isinstance(o.get('호내용'), str): lines.append(o['호내용'])
            arts[no] = lines
    cache[name] = arts
    CACHE.write_text(json.dumps(cache, ensure_ascii=False))
    return arts

def squash(s): return re.sub(r'\s+', '', s)
def near_dates(d):
    x = dt.date.fromisoformat(d); return [x + dt.timedelta(days=k) for k in (-1, 0, 1)]
def has_date(text, d):
    t = squash(text)
    for x in near_dates(d):
        for f in (x.isoformat(), f'{x.year}년{x.month}월{x.day}일', f'{x.year}.{x.month}.{x.day}', f'{x.year}.{x.month:02d}.{x.day:02d}', f'{x.year}/{x.month:02d}/{x.day:02d}'):
            if f in t: return True
    return False

def main():
    who, mode = sys.argv[1], sys.argv[2]
    out = OUT / who / mode / 'out'
    exp = json.loads((OUT / '_oracle' / f'expected_{mode}.json').read_text())
    consult = dt.date.fromisoformat(exp['consult_date'])
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    checks, notes = [], {}
    def add(name, ok, detail=''): checks.append({'check': name, 'ok': bool(ok), 'detail': detail})
    memos = {p.stem: p.read_text() for p in sorted((out / 'cases').glob('*.md'))} if (out / 'cases').exists() else {}
    index = None
    try:
        index = json.loads((out / 'index.json').read_text()); index = index.get('items', index.get('cases', index)) if isinstance(index, dict) else index
    except Exception as e: notes['index_error'] = str(e)
    summary = (out / 'summary.md').read_text() if (out / 'summary.md').exists() else ''
    ids = list(exp['cases'])
    add('파일: 메모 전건·index 행수·summary', all(i in memos for i in ids) and isinstance(index, list) and len(index) == len(ids) and bool(summary), f'memos {len(memos)}/{len(ids)}, index {len(index) if isinstance(index, list) else None}')
    add('메모마다 법률 자문 아님 표시', all(re.search(r'법률\s*자문', memos.get(i, '')) for i in ids), str([i for i in ids if not re.search(r'법률\s*자문', memos.get(i, ''))]))
    quoted, need_quote, bad_pairs, unknown_pairs = [], [], [], 0
    names = sorted({e['law'] for e in exp['cases'].values() if e.get('law')})
    official = {n: law_articles(n, cache) for n in names}
    for cid, e in exp['cases'].items():
        m = memos.get(cid, ''); sq = squash(m)
        if e.get('law'):
            need_quote.append(cid)
            arts = official[e['law']]
            hit = [a for a in e['articles'] if any(len(squash(l)) >= 15 and squash(l) in sq for l in arts.get(a, []))]
            if hit: quoted.append(cid)
            notes.setdefault('quoted_articles', {})[cid] = hit
        for n in names:   # "법령명 제N조" 쌍이 그 법에 실재하는가
            for a in re.findall(re.escape(n) + r'[」\s]*\s*(제\d+조(?:의\d+)?)', m):
                if a not in official[n]: bad_pairs.append([cid, n, a])
    add(f'기대 조문 원문 인용(공식 원문 줄과 일치) {len(quoted)}/{len(need_quote)}', len(quoted) == len(need_quote), str(sorted(set(need_quote) - set(quoted))))
    add('법령명+조 번호 쌍이 공식 원문에 실재(없는 쌍 0)', not bad_pairs, str(bad_pairs))
    for cid, e in exp['cases'].items():
        m = memos.get(cid, '')
        if e['kind'] == 'deadline':
            days = (dt.date.fromisoformat(e['deadline']) - consult).days
            d_ok = has_date(m, e['deadline'])
            n_ok = any(re.search(rf'(?<!\d){abs(days) + k}\s*일', m) for k in (-1, 0, 1)) or (days == 0 and re.search('당일|오늘|0일', m))
            past_ok = days >= 0 or re.search('지남|지났|지난|경과|도과|넘', m)
            add(f'{cid} 기한 {e["deadline"]}({days}일)', d_ok and n_ok and past_ok, f'date {d_ok} days {bool(n_ok)} past {bool(past_ok)}')
        elif e['kind'] == 'need_date':
            add(f'{cid} 날짜 확인 필요(기한 지어내지 않음)', re.search(r'날짜.{0,15}확인|확인.{0,15}날짜|[종만]료일.{0,25}확인|확인 필요', m) is not None)
        elif e['kind'] == 'empty':
            add(f'{cid} 빈 접수지 표시', cid in memos and re.search('내용이? ?없|비어|빈 접수', m) is not None)
        if e.get('claimed'):
            pos = [x.start() for x in re.finditer(re.escape(e['claimed']), m)]
            add(f'{cid} 주장한 법 「{e["claimed"]}」 없음 표시', any(re.search('없|찾지 못|존재하지|확인되지|미확인', m[p:p + 160]) for p in pos), f'mentions {len(pos)}')
    case_no = re.compile(r'\d{2,4}\s?[가-힣]{1,3}\s?\d{2,7}')
    real = [i for i in ids if exp['cases'][i]['kind'] != 'empty']
    add('판례: 건마다 사건번호 또는 못 찾음', all(case_no.search(memos.get(i, '')) or re.search('못 찾|찾지 못|없음', memos.get(i, '')) for i in real))
    notes['prec_attached'] = [i for i in real if re.search(r'선고', memos.get(i, '')) and case_no.search(memos.get(i, '')) and not re.search(r'## 판례\s*\n못 찾음', memos.get(i, ''))]
    rows = [r for r in (index or []) if isinstance(r, dict) and r.get('prec_id')]
    if rows:
        bad = []
        for r in rows:
            v = ibl(f'$d = [sense:legal]{{id:"{r["prec_id"]}",target:"prec"}}\nreturn get(get($d,"PrecService"),"사건번호")')
            if squash(str(v)) != squash(str(r.get('prec_case_no'))): bad.append([r['id'], r.get('prec_case_no'), v])
        add(f'붙인 판례 {len(rows)}건이 원천에 실재(재조회)', not bad, str(bad))
    else:
        add('붙인 판례가 원천에 실재(재조회)', False, 'index 에 판례 식별값이 없어 재조회하지 못함 — 미검증'); checks[-1]['unverified'] = True
    dl = sorted([(  (dt.date.fromisoformat(e['deadline']) - consult).days, cid) for cid, e in exp['cases'].items() if e['kind'] == 'deadline'])
    want = [c for _, c in dl]
    tbl = '\n'.join(l for l in summary.splitlines() if l.strip().startswith('|'))
    pos = {c: tbl.find(c) for c in ids}
    got = [c for c in sorted(want, key=lambda c: pos[c]) if pos[c] >= 0]
    rest = [pos[c] for c in ids if c not in want and pos[c] >= 0]
    add('summary 급한 순', got == want and all(p > max(pos[c] for c in want) for p in rest), f'want {want} got {got}')
    add('summary 확인하지 못한 것 절', re.search('확인하지 못|확인 못|미확인', summary) is not None)
    ok = sum(c['ok'] for c in checks)
    (HERE / 'evidence' / f'{who}_{mode}_qa.json').write_text(json.dumps({'who': who, 'mode': mode, 'score': f'{ok}/{len(checks)}', 'checks': checks, 'notes': notes}, ensure_ascii=False, indent=1))
    print(who, mode, f'{ok}/{len(checks)}')
    for c in checks:
        if not c['ok']: print('  ✗', c['check'], '|', c['detail'][:300])
    print('  notes', json.dumps(notes, ensure_ascii=False)[:600])

if __name__ == '__main__':
    main()
