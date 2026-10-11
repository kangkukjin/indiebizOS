"""55회차 검수 — 산출물을 정답표·따로 가져온 원천과 대조. 사용: verify.py <mode> [--who trainer] [--out DIR]
원천(e약은요 검색·상세, PubMed)은 프로그램과 다른 길(urllib 직접)로 가져온다. 결과는 evidence/<who>_<mode>_qa.json."""
import argparse, html, json, re, sys, time, urllib.parse, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
OUT = HERE.parents[3] / 'outputs/long_sentence_imagination/2026-10-11_55회차'
UA = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126 Safari/537.36'}
EXPECT_DRUGS = {  # 접수지에 적힌 약: (찾음 기대, whose, status)
 'H01': {'타이레놀정500밀리그람': (True, '본인', 'current'), '타이레놀콜드-에스정': (True, '본인', 'current')},
 'H02': {'노바스크정5밀리그램': (False, '본인', 'current')}, 'H03': {'지르텍정': (True, '본인', 'current')},
 'H04': {'이지엔6애니연질캡슐': (True, '본인', 'current'), '탁센연질캡슐': (True, '본인', 'current')},
 'H05': {'하늘맑음정': (False, '본인', 'current'), '판콜에스내복액': (True, '본인', 'current')},
 'H06': {'게보린정': (True, '본인', 'stopped'), '타이레놀정500밀리그람': (True, '본인', 'current')},
 'H07': {'게보린정': (True, '본인', 'current'), '판콜에스내복액': (True, '본인', 'current')},
 'H08': {'아스피린프로텍트정100밀리그람': (True, '본인', 'current')},
 'H09': {'지르텍정': (True, '본인', 'current'), '아스피린프로텍트정100밀리그람': (True, '타인', 'current')}, 'H10': {},
 'K04': {'어린이타이레놀현탁액': (True, '본인', 'current'), '판콜에스내복액': (True, '본인', 'current')}, 'K03': {},
 'K02': {'탁센연질캡슐': (True, '본인', 'current')}, 'K01': {'지르텍정': (True, '본인', 'current'), '달빛고요캡슐': (False, '본인', 'current')},
}
OPTIONAL = {('H09', '아스피린프로텍트정100밀리그람')}   # 다른 사람 약은 목록에 없어도 된다
BAN = ['진단됩니다', '로 진단', '용량을 늘리', '용량을 줄이', '줄이세요', '늘리세요', '복용을 중단하세요', '끊으세요']
_cache = {}


def fetch(url):
    if url not in _cache:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
            _cache[url] = r.read().decode('utf-8', 'replace')
    return _cache[url]


def squash(s): return re.sub(r'\s+', '', html.unescape(re.sub(r'</?[A-Za-z!][^>]*>', '', s)))
def nows(s): return re.sub(r'\s+', '', s)   # 인용문 쪽 — 글 안의 '<' 를 태그로 지우지 않는다
def norm_ing(s): return s.split('(')[0].replace('과립', '').strip()


def source_drug(name):
    """e약은요 검색에서 제품명이 name 으로 시작하는 첫 품목의 (품목기준코드, 주성분 집합, 상세 본문)"""
    page = fetch('https://nedrug.mfds.go.kr/searchEasyDrug?itemName=' + urllib.parse.quote(name))
    for m in re.finditer(r'getItemDetail\?itemSeq=(\d+)[^>]*>\s*([^<]+?)\s*</a>', page):
        seq, title = m.group(1), html.unescape(m.group(2)).strip()
        if title.startswith(name):
            tail = page[m.end():m.end() + 3000]
            ing = re.search(r'주성분</span>\s*([^<]+)<', tail) or re.search(r'주성분[^<]*</[^>]+>\s*(?:<[^>]+>\s*)*([^<]+)<', tail)
            ings = {norm_ing(x) for x in html.unescape(ing.group(1)).split(',') if x.strip()} if ing else None
            return seq, ings, squash(fetch('https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq=' + seq))
    return None, None, ''


def pmid_exists(pmid):
    try:
        time.sleep(0.5)   # NCBI 는 열쇠 없이 초당 3회까지
        d = json.loads(fetch(f'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&retmode=json&id={pmid}'))
        return 'error' not in d.get('result', {}).get(str(pmid), {'error': 1})
    except Exception as e:
        return f'조회 실패 {e}'


def close(a, b): return (a is None and b is None) or (a is not None and b is not None and abs(a - b) <= 0.11)


def main():
    p = argparse.ArgumentParser(); p.add_argument('mode'); p.add_argument('--who', default='trainer'); p.add_argument('--out'); p.add_argument('--label'); a = p.parse_args()
    base = OUT / a.who / a.mode; out = Path(a.out) if a.out else base / 'out'
    exp = json.loads(((OUT / 'trainer' / a.mode) / '_oracle/expected.json').read_text())
    res, notes = {}, []
    def chk(name, ok, note=''):
        res[name] = bool(ok)
        if not ok: notes.append(f'{name}: {note}'[:600])
    try: index = json.loads((out / 'index.json').read_text())
    except Exception as e: index = None; notes.append(f'index.json 못 읽음: {e}')
    if not exp['ids']:   # 변형 C
        chk('빈 접수: 메모를 지어내지 않음', not list((out / 'cases').glob('*.md')) if (out / 'cases').exists() else True)
        chk('빈 접수: index 빈 배열 또는 없음', index in ([], None))
        chk('빈 접수: 접수 없음 표시', (out / 'summary.md').exists() and '접수 없음' in (out / 'summary.md').read_text() or index is None)
    else:
        index = index or []
        by = {r.get('id'): r for r in index}
        memos = {i: (out / 'cases' / f'{i}.md').read_text() if (out / 'cases' / f'{i}.md').exists() else '' for i in exp['ids']}
        chk('1 메모·index·summary 전건', all(memos.values()) and sorted(by) == exp['ids'] and (out / 'summary.md').exists(), f'index ids {sorted(by)}')
        chk('1 의료 자문 아님 표시', all('자문' in m and any(w in m for w in ('아님', '아니', '아닙')) for m in memos.values()))
        chk('2 급한 순', [r.get('id') for r in index] == exp['order'], f"{[r.get('id') for r in index]} != {exp['order']}")
        chk('2 urgent', sorted(r['id'] for r in index if r.get('urgent')) == exp['urgent'], str(sorted(r['id'] for r in index if r.get('urgent'))))
        bad = []
        for cid in exp['ids']:
            got = (by.get(cid) or {}).get('stats') or {}; want = exp['stats'].get(cid, {})
            if set(got) != set(want): bad.append(f'{cid} 종류 {sorted(got)}!={sorted(want)}'); continue
            for k, w in want.items():
                for f, v in w.items():
                    g = got[k].get(f)
                    if not (g == v if f in ('n', 'invalid', 'over_days') else close(g, v)): bad.append(f'{cid}.{k}.{f} {g}!={v}')
        chk('3 측정 통계', not bad, '; '.join(bad[:8]))
        dbad, ibad, qbad, dupbad, unv = [], [], [], [], []
        for cid in exp['ids']:
            drugs = {d.get('name'): d for d in (by.get(cid) or {}).get('drugs') or []}
            want = EXPECT_DRUGS[cid]
            miss = [n for n in want if n not in drugs and (cid, n) not in OPTIONAL]
            extra = [n for n in drugs if n not in want]
            if miss or extra: dbad.append(f'{cid} 빠짐 {miss} 더함 {extra}')
            mine = []
            for n, (found, whose, status) in want.items():
                d = drugs.get(n)
                if d is None: continue
                if d.get('found') != found or d.get('whose') != whose or d.get('status') != status: dbad.append(f"{cid} {n} found={d.get('found')} whose={d.get('whose')} status={d.get('status')}")
                if not found:
                    if d.get('ingredients'): ibad.append(f'{cid} {n} 못 찾은 약에 성분')
                    if '확인하지 못함' not in memos[cid]: unv.append(cid)
                    continue
                seq, ings, body = source_drug(n)
                if ings is None or {norm_ing(x) for x in d.get('ingredients') or []} != ings: ibad.append(f"{cid} {n} {d.get('ingredients')} != {ings}")
                if str(d.get('item_seq')) != str(seq): ibad.append(f"{cid} {n} seq {d.get('item_seq')}!={seq}")
                if whose == '본인' and status == 'current': mine.append(ings or set())
                sec = memos[cid].split('### ' + n, 1)[1] if '### ' + n in memos[cid] else (memos[cid].split(n, 1)[1] if n in memos[cid] else '')   # 약 이름은 경과 글에도 나온다 — 약 절의 제목부터
                sec = re.split(r'\n#{2,3} ', sec, maxsplit=1)[0]
                quotes = [q.strip()[1:].strip() for q in sec.splitlines() if q.strip().startswith('>') and q.strip()[1:].strip() and not q.strip()[1:].strip().startswith('(')]
                if not quotes and '비어 있' not in sec: qbad.append(f'{cid} {n} 인용 없음')   # 원천 대목이 비었다고 적은 것은 인용 없음이 아니다
                qbad += [f'{cid} {n} 원문에 없음: {q[:50]}' for q in quotes if nows(q) not in body]
            flat = [g for s in mine for g in s]
            dup = sorted({g for g in flat if flat.count(g) > 1})
            if sorted(norm_ing(x) for x in (by.get(cid) or {}).get('duplicate_ingredients') or []) != dup: dupbad.append(f"{cid} {(by.get(cid) or {}).get('duplicate_ingredients')} != {dup}")
        chk('4 약 목록·찾음·whose·status', not dbad, '; '.join(dbad[:6]))
        chk('4 성분·품목코드 = 따로 가져온 원천', not ibad, '; '.join(ibad[:6]))
        chk('4 못 찾은 약: 확인하지 못함 표시', not unv, str(unv))
        chk('5 겹치는 성분', not dupbad, '; '.join(dupbad[:6]))
        if 'H07' in by: chk('5 H07 게보린 dose=null', any(d.get('name') == '게보린정' and d.get('dose') is None for d in by['H07'].get('drugs') or []))
        chk('6 주의 인용문 ⊂ 상세 원문', not qbad, '; '.join(qbad[:6]))
        pbad = []
        for cid in exp['ids']:
            pt = (by.get(cid) or {}).get('portal') or {}
            if pt.get('status') == 'quoted':
                try: body = squash(fetch(pt.get('url')))
                except Exception as e: body = ''
                hm = re.search(r'\n## [^\n]*병원[^\n]*\n', memos[cid]); sec = memos[cid][hm.end():] if hm else ''   # '병원' 은 경과 글에도 나온다 — 그 절의 제목부터
                qs = [q.strip()[1:].strip() for q in re.split(r'\n## ', sec, maxsplit=1)[0].splitlines() if q.strip().startswith('>') and q.strip()[1:].strip() and not q.strip()[1:].strip().startswith('(')]
                if not qs or any(nows(q) not in body for q in qs): pbad.append(f'{cid} 인용 미확인')
            elif not (pt.get('status') == 'unverified' and ('읽지 못' in memos[cid] or '못 읽' in memos[cid] or '확인하지 못' in memos[cid])): pbad.append(f'{cid} {pt}')
        chk('7 병원 갈 신호: 원문 인용 또는 정직한 미확인', not pbad, '; '.join(pbad[:6]))
        res['7 참고: quoted 건수'] = sum(1 for r in index if (r.get('portal') or {}).get('status') == 'quoted')
        mbad = []
        for cid in exp['ids']:
            pm = (by.get(cid) or {}).get('pmids') or []
            if not pm and '못 찾' not in memos[cid]: mbad.append(f'{cid} 빈 pmids 인데 표시 없음')
            mbad += [f'{cid} PMID {x}: {r}' for x in pm for r in [pmid_exists(x)] if r is not True]
        chk('8 논문 실재 또는 못 찾음', not mbad, '; '.join(mbad[:6]))
        res['8 참고: 논문 붙은 건수'] = sum(1 for r in index if r.get('pmids'))
        ban = [f'{cid}:{w}' for cid, m in memos.items() for w in BAN if w in m]
        chk('9 진단 단정·용량 변경 권고 낱말 없음', not ban, str(ban))
        if 'H10' in memos: chk('10 H10 상대 날짜 2026-10-06', '2026-10-06' in memos['H10'])
    passed = sum(1 for k, v in res.items() if v is True); total = sum(1 for v in res.values() if isinstance(v, bool))
    rec = {'who': a.who, 'mode': a.mode, 'passed': passed, 'total': total, 'results': res, 'notes': notes}
    (HERE / 'evidence' / f'{a.label or a.who + "_" + a.mode}_qa.json').write_text(json.dumps(rec, ensure_ascii=False, indent=1))
    print(json.dumps(rec, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
