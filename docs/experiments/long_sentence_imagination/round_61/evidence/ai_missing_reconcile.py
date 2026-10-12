import json, sys, os, re, unicodedata, collections

IN, OUT = sys.argv[1], sys.argv[2]
NFC = lambda s: unicodedata.normalize('NFC', s) if isinstance(s, str) else s
SIGN = {'입고': 1, '반품': 1, '출고': -1}
# 표기 변형 흡수 규칙(관측된 경우만 보고)
KIND_ALIAS = {'in': '입고', 'inbound': '입고', 'receipt': '입고', 'out': '출고', 'outbound': '출고',
              'shipment': '출고', 'return': '반품', 'returns': '반품'}

man = json.load(open(os.path.join(IN, 'manifest.json'), encoding='utf-8'))
files = man['files']
stock = json.load(open(os.path.join(IN, 'stock.json'), encoding='utf-8'))

notes = []
raw = []          # (file, idx, row)
file_status = []
missing = []
for f in files:
    p = os.path.join(IN, f)
    try:
        data = json.loads(open(p, 'rb').read().decode('utf-8'))
        if not isinstance(data, list):
            raise ValueError('최상위가 배열이 아님')
        for i, r in enumerate(data):
            raw.append((f, i, r))
        file_status.append({'file': f, 'status': 'ok', 'rows': len(data)})
    except Exception as e:
        missing.append({'file': f, 'reason': f'{type(e).__name__}: {e}'[:300]})
        file_status.append({'file': f, 'status': 'failed', 'rows': 0, 'reason': missing[-1]['reason']})

# 정규화
kind_variants = collections.Counter()
nfd_event_rows = 0
bad_rows = []
def norm(r):
    global nfd_event_rows
    wh = r.get('warehouse')
    if isinstance(wh, str) and not unicodedata.is_normalized('NFC', wh):
        nfd_event_rows += 1
    k = r.get('kind', r.get('type'))
    kn = NFC(k.strip()) if isinstance(k, str) else k
    if isinstance(kn, str) and kn not in SIGN:
        alias = KIND_ALIAS.get(kn.lower())
        if alias:
            kind_variants[(k, alias)] += 1
            kn = alias
    elif isinstance(k, str) and kn != k:
        kind_variants[(k, kn)] += 1
    return {'id': r.get('id'), 'version': r.get('version'), 'sku': NFC(r.get('sku')),
            'warehouse': NFC(wh), 'kind': kn, 'qty': r.get('qty')}

normed = [(f, i, norm(r)) for f, i, r in raw]

# id별 최신판
by_id = collections.defaultdict(list)
for f, i, r in normed:
    by_id[r['id']].append((f, i, r))
latest = {}
version_conflicts = []
identical_dup_latest = []
for eid, lst in by_id.items():
    mv = max(r['version'] for _, _, r in lst)
    tops = [(f, i, r) for f, i, r in lst if r['version'] == mv]
    distinct = {json.dumps(r, sort_keys=True, ensure_ascii=False) for _, _, r in tops}
    if len(distinct) > 1:
        version_conflicts.append({'id': eid, 'version': mv,
                                  'candidates': [dict(r, file=f, index=i) for f, i, r in tops]})
    elif len(tops) > 1:
        identical_dup_latest.append({'id': eid, 'version': mv, 'copies': len(tops),
                                     'files': sorted({f for f, _, _ in tops})})
    latest[eid] = tops[0][2]

raw_rows = len(raw)
unique_ids = len(latest)
excluded = raw_rows - unique_ids
assert raw_rows == unique_ids + excluded
conflict_ids = {c['id'] for c in version_conflicts}

# 조합 집계
agg = collections.defaultdict(lambda: {'net': 0, 'ids': [], 'unknown': [], 'bad': []})
for eid in sorted(latest):
    r = latest[eid]
    key = (r['sku'], r['warehouse'])
    a = agg[key]
    a['ids'].append(eid)
    if eid in conflict_ids:
        a['unknown'].append(eid)          # 같은 최신판 내용 충돌 → 수량 미확정
    elif r['kind'] not in SIGN:
        a['bad'].append(eid)
    elif r['qty'] is None:
        a['unknown'].append(eid)
    elif not isinstance(r['qty'], (int, float)) or isinstance(r['qty'], bool):
        a['bad'].append(eid)
    else:
        a['net'] += SIGN[r['kind']] * r['qty']

incomplete = len(missing) > 0
stock_keys = set()
rows = []
for s in stock:
    key = (NFC(s['sku']), NFC(s['warehouse']))
    stock_keys.add(key)
    a = agg.get(key, {'net': 0, 'ids': [], 'unknown': [], 'bad': []})
    unk = a['unknown'] + a['bad']
    if incomplete or unk:
        exp = diff = None
        status = '미확인'
    else:
        exp = s['opening'] + a['net']
        diff = s['counted'] - exp
        status = '일치' if diff == 0 else '차이'
    reasons = []
    if a['unknown']: reasons.append('수량 미상 전표')
    if a['bad']: reasons.append('유형/수량 판독 불가 전표')
    if incomplete: reasons.append('전표 파일 누락')
    rows.append({'sku': s['sku'], 'warehouse': s['warehouse'], 'warehouse_nfc': key[1],
                 'opening': s['opening'], 'confirmed_net': a['net'], 'counted': s['counted'],
                 'expected': exp, 'diff_counted_minus_expected': diff, 'status': status,
                 'unknown_qty_ids': a['unknown'], 'unreadable_ids': a['bad'],
                 'status_reason': reasons, 'evidence_ids': a['ids']})

unregistered = []
for key in sorted(k for k in agg if k not in stock_keys):
    a = agg[key]
    unregistered.append({'sku': key[0], 'warehouse': key[1], 'confirmed_net': a['net'],
                         'unknown_qty_ids': a['unknown'],
                         'events': [dict(latest[e]) for e in a['ids']], 'evidence_ids': a['ids']})

unknown_events = [dict(latest[e], in_stock=(latest[e]['sku'], latest[e]['warehouse']) in stock_keys)
                  for e in sorted(latest) if latest[e]['qty'] is None or e in conflict_ids]
superseded_null = sorted({r['id'] for _, _, r in normed if r['qty'] is None} - {e['id'] for e in unknown_events})

status_counts = collections.Counter(r['status'] for r in rows)
result = {
    'inputs': {'manifest_files': files, 'file_status': file_status, 'stock_rows': len(stock)},
    'counts': {'raw_event_rows': raw_rows, 'unique_events': unique_ids,
               'excluded_by_latest_selection': excluded,
               'stock_rows': len(rows),
               'status': {k: status_counts.get(k, 0) for k in ['일치', '차이', '미확인']}},
    'missing_files': missing,
    'unknown_qty_events': unknown_events,
    'unregistered_combinations': unregistered,
    'rows': rows,
    'anomalies': {
        'nfd_warehouse_event_rows': nfd_event_rows,
        'nfd_warehouse_stock_rows': sum(1 for s in stock if not unicodedata.is_normalized('NFC', s['warehouse'])),
        'kind_variants': [{'raw': k, 'normalized_to': v, 'rows': n} for (k, v), n in kind_variants.items()],
        'latest_version_content_conflicts': version_conflicts,
        'identical_latest_duplicates': len(identical_dup_latest),
        'ids_with_multiple_rows': sum(1 for l in by_id.values() if len(l) > 1),
        'null_qty_superseded_by_newer_version': superseded_null,
    },
    'rules': ['같은 id는 최대 version 한 건만 사용, 같은 최신판의 반복은 한 건',
              '묶음 키 = (sku, NFC 정규화 warehouse)', '입고·반품 +, 출고 −',
              'qty null 최신판은 0으로 보지 않음 → 확인된 순증감에서 제외, 예상재고·차이 null, 상태 미확인',
              '같은 id·같은 최신 version인데 내용이 다르면 수량 미확정으로 보아 미상과 같이 처리',
              '전표 파일 하나라도 읽기 실패 시 모든 행의 예상재고·차이 null, 상태 미확인',
              '예상재고 = 기초재고 + 확인된 순증감, 차이 = 실사재고 − 예상재고'],
}
os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT, 'result.json'), 'w', encoding='utf-8') as fp:
    json.dump(result, fp, ensure_ascii=False, indent=2)

# report.md
c = result['counts']
esc = lambda s: str(s).replace('|', '\\|')
L = ['# 창고 재고 대조 보고서', '',
     '## 요약', '',
     f"- 전표 파일: manifest {len(files)}개 중 읽음 {len(files)-len(missing)}개, 누락 {len(missing)}개",
     f"- 원본 전표 행수: {c['raw_event_rows']}",
     f"- 고유 전표수(id별 최신판): {c['unique_events']}",
     f"- 최신판 선택으로 제외된 행수: {c['excluded_by_latest_selection']} (원본 = 고유 + 제외: {c['raw_event_rows']} = {c['unique_events']} + {c['excluded_by_latest_selection']})",
     f"- 대조 행(stock.json 품목·창고) 전체: {c['stock_rows']}건",
     f"- 상태별: 일치 {c['status']['일치']}건 · 차이 {c['status']['차이']}건 · 미확인 {c['status']['미확인']}건",
     f"- 수량 미상 전표: {len(unknown_events)}건 · 미등록 조합: {len(unregistered)}개", '',
     '## 계산 규칙', ''] + [f'- {x}' for x in result['rules']] + ['',
     '## 자료 특이사항', '',
     f"- 전표 창고명 NFD 표기 행: {nfd_event_rows}행 → NFC로 정규화해 같은 창고로 통합",
     f"- stock.json 창고명 NFD 표기 행: {result['anomalies']['nfd_warehouse_stock_rows']}행",
     f"- 유형(kind) 표기 변형: " + (', '.join(f"{v['raw']!r}→{v['normalized_to']} {v['rows']}행" for v in result['anomalies']['kind_variants']) or '없음 (입고·출고·반품 세 값만 관측)'),
     f"- 여러 행을 가진 id: {result['anomalies']['ids_with_multiple_rows']}개, 그중 같은 최신판이 반복된 id: {len(identical_dup_latest)}개 (한 건으로 계산)",
     f"- 같은 version인데 내용이 다른 충돌: " + (', '.join(v['id'] for v in version_conflicts) or '없음 (NFC 정규화 후 비교)'),
     f"- 구판에서만 qty null이고 최신판에서 수량이 확정된 id: " + (', '.join(superseded_null) or '없음'), '',
     '## 누락 파일', '']
L += [f"- {m['file']}: {m['reason']}" for m in missing] or ['- 없음 (네 파일 모두 읽고 파싱함)']
L += ['', '## 수량 미상 전표', '']
if unknown_events:
    L += ['| id | version | sku | 창고 | 유형 | qty | stock 등록 |', '|---|---|---|---|---|---|---|']
    L += [f"| {e['id']} | {e['version']} | {e['sku']} | {esc(e['warehouse'])} | {e['kind']} | null | {'예' if e['in_stock'] else '아니오'} |" for e in unknown_events]
else:
    L.append('- 없음')
L += ['', '## 미등록 조합 전표 (stock.json에 없는 sku·창고)', '']
if unregistered:
    L += ['| sku | 창고 | 확인된 순증감 | 미상 id | 전표(id·유형·qty) |', '|---|---|---|---|---|']
    for u in unregistered:
        ev = ', '.join(f"{e['id']}({e['kind']} {e['qty']})" for e in u['events'])
        L.append(f"| {u['sku']} | {esc(u['warehouse'])} | {u['confirmed_net']} | {', '.join(u['unknown_qty_ids']) or '-'} | {ev} |")
else:
    L.append('- 없음')
L += ['', '## 품목별 대조 표', '',
      '| sku | 창고 | 기초재고 | 확인된 순증감 | 실사재고 | 예상재고 | 실사-예상 차이 | 상태 | 미상 id | 근거 전표 id |',
      '|---|---|---|---|---|---|---|---|---|---|']
fmt = lambda v: 'null' if v is None else str(v)
for r in rows:
    L.append(f"| {r['sku']} | {esc(r['warehouse'])} | {r['opening']} | {r['confirmed_net']} | {r['counted']} | {fmt(r['expected'])} | {fmt(r['diff_counted_minus_expected'])} | {r['status']} | {', '.join(r['unknown_qty_ids'] + r['unreadable_ids']) or '-'} | {', '.join(r['evidence_ids']) or '-'} |")
L += ['', '전체 수치와 근거는 같은 폴더의 result.json에 있습니다. 입력 파일(stock.json·전표)은 수정하지 않았습니다.', '']
with open(os.path.join(OUT, 'report.md'), 'w', encoding='utf-8') as fp:
    fp.write('\n'.join(L))

# 재독 대조
R = json.load(open(os.path.join(OUT, 'result.json'), encoding='utf-8'))
md = open(os.path.join(OUT, 'report.md'), encoding='utf-8').read()
table_rows = [l for l in md.split('\n') if l.startswith('| P') or l.startswith('| ')]
main_table = md.split('## 품목별 대조 표')[1]
mt_rows = [l for l in main_table.split('\n') if l.startswith('| ') and not l.startswith('| sku') ]
sc = collections.Counter(r['status'] for r in R['rows'])
checks = {
    'raw=unique+excluded': R['counts']['raw_event_rows'] == R['counts']['unique_events'] + R['counts']['excluded_by_latest_selection'],
    'stock rows preserved': len(R['rows']) == len(stock) and [(r['sku'], r['warehouse']) for r in R['rows']] == [(s['sku'], s['warehouse']) for s in stock],
    'status counts match': dict(sc) == {k: v for k, v in R['counts']['status'].items() if v},
    'status sum = rows': sum(R['counts']['status'].values()) == len(R['rows']),
    'report table rows': len(mt_rows) == len(R['rows']),
    'report cells 10 per row': all(len(re.split(r'(?<!\\)\|', l.strip())[1:-1]) == 10 for l in mt_rows),
    'report status line': f"일치 {sc.get('일치',0)}건 · 차이 {sc.get('차이',0)}건 · 미확인 {sc.get('미확인',0)}건" in md,
    'evidence ids cover all registered latest': sum(len(r['evidence_ids']) for r in R['rows']) + sum(len(u['evidence_ids']) for u in R['unregistered_combinations']) == R['counts']['unique_events'],
    'null rows have null expected': all((r['expected'] is None) == (r['status'] == '미확인') for r in R['rows']),
    'expected arithmetic': all(r['expected'] is None or (r['expected'] == r['opening'] + r['confirmed_net'] and r['diff_counted_minus_expected'] == r['counted'] - r['expected']) for r in R['rows']),
}
print(json.dumps({'counts': R['counts'], 'missing': R['missing_files'], 'unknown': [e['id'] for e in R['unknown_qty_events']],
                  'unregistered': [(u['sku'], u['warehouse'], u['evidence_ids']) for u in R['unregistered_combinations']],
                  'anomalies': {k: v for k, v in R['anomalies'].items() if k != 'latest_version_content_conflicts'},
                  'conflicts': R['anomalies']['latest_version_content_conflicts'],
                  'checks': checks}, ensure_ascii=False, indent=1))
