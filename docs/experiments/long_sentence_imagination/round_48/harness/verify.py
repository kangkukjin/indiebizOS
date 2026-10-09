"""결정론 검수 — 산출물(result.json·report.md·display.csv) + 서버 state(진짜 저장) + oracle. 사용: verify.py <who> <mode> [--site-key KEY] [--out SUB]"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import site_server
ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-10_48회차'
HERE = Path(__file__).resolve().parent.parent
def main():
    who, mode = sys.argv[1], sys.argv[2]
    sub = {'base': 'out', 'flaky': 'out_flaky', 'b': 'out_b'}[mode]; key = who + {'base': '', 'flaky': '_flaky', 'b': '_b'}[mode]
    if '--out' in sys.argv: sub = sys.argv[sys.argv.index('--out') + 1]
    if '--site-key' in sys.argv: key = sys.argv[sys.argv.index('--site-key') + 1]
    exp = json.loads((OUT / '_oracle/expected.json').read_text()); st = json.loads((OUT / '_site' / f'{key}.json').read_text())
    out = OUT / who / sub; res = json.loads((out / 'result.json').read_text()); rep = (out / 'report.md').read_text() if (out / 'report.md').exists() else ''
    pol = exp['policy_b'] if mode == 'b' else exp['policy']; e = exp['b' if mode == 'b' else 'base']; ids = e['edit_ids']; fail = exp['fail_once'] if mode == 'flaky' else None
    seed = site_server.seed(); fin = st['final']; checks = []
    def c(name, cond, detail=None): checks.append({'check': name, 'ok': bool(cond), 'detail': detail})
    want = {ids[x['name']]: x for x in pol['edits']}
    c('서버: 방침 가격·문구 저장', all(fin[i]['price'] == x['price'] and fin[i]['desc'] == x['desc'] for i, x in want.items()), {i: [fin[i]['price'], fin[i]['desc']] for i in want})
    changed = sorted(i for i in fin if fin[i] != seed[i]); c('서버: 다른 상품 변경 0', changed == sorted(want), changed)
    c('편집 화면은 방침 상품만', sorted(set(st['edit_views'])) == sorted(want), st['edit_views'])
    c('자동완성 사용·선택이 방침 상품', len(st['suggest']) >= 1 and sorted(set(st['picks'])) == sorted(want), {'suggest': st['suggest'], 'picks': st['picks']})
    c('서버: 진열 순서 = 방침', st['display'] == e['order'], st['display'])
    c('내보내기·내려받기 성공 기록', st['exports'] >= 1 and len(st['downloads']) >= 1, {'exports': st['exports'], 'downloads': len(st['downloads']), 'denied': len(st['denied'])})
    csvp = out / 'display.csv'; raw = csvp.read_bytes() if csvp.exists() else b''
    srv = '﻿' + '\r\n'.join(['순위,상품번호,상품명,판매가,진열 문구'] + [f'{k + 1},{i},{fin[i]["name"]},{fin[i]["price"]},"{fin[i]["desc"]}"' for k, i in enumerate(st['display'])]) + '\r\n'
    norm = lambda s: s.lstrip('﻿').replace('\r\n', '\n').strip()
    c('display.csv 내용 = 서버 파일(8행)', csvp.exists() and norm(raw.decode('utf-8', 'replace')) == norm(srv) and len(st['display']) == 8, {'bytes': len(raw)})
    c('display.csv 바이트까지 같음(BOM·CRLF)', raw == srv.encode(), {'got': len(raw), 'server': len(srv.encode()), 'bom': raw[:3] == b'\xef\xbb\xbf', 'crlf': b'\r\n' in raw})
    ex = res.get('export', {}); c('보고: CSV 대조 결과', ex.get('match') is True and ex.get('rows') == 8, {'match': ex.get('match'), 'rows': ex.get('rows')})
    off = sorted(x['name'] for x in pol['edits'] if ids[x['name']] not in st['display'])
    c('보고: 파일로 확인 못 한 상품', sorted(ex.get('not_in_csv', [])) == off, ex.get('not_in_csv'))
    bk = res.get('back', {}); c('뒤로 가기 뒤 순서 확인', bk.get('match') is True and '/display' in str(bk.get('url')), bk.get('url'))
    failed = res.get('network', {}).get('failed', [])
    if fail:
        log = [s for s in st['saves'] if s['id'] == fail]
        c('서버: 첫 저장 500 뒤 재시도 성공', [s['ok'] for s in log] == [False, True], [s['ok'] for s in log])
        c('보고: 시도 2회', [x.get('attempts') for x in res.get('edits', []) if x.get('id') == fail] == [2], [(x.get('id'), x.get('attempts')) for x in res.get('edits', [])])
        c('보고: 네트워크 기록의 500', len(failed) == 1 and failed[0].get('status') == 500 and '/api/save' in failed[0].get('url', ''), failed)
    else:
        c('서버: 저장 시도 = 상품 수(실패 0)', len(st['saves']) == len(want) and all(s['ok'] for s in st['saves']), [(s['id'], s['ok']) for s in st['saves']])
        c('보고: 네트워크 실패 0건', failed == [] and res.get('network', {}).get('capturing') is True, failed)
    c('보고: 판정 완료', '완료' in res.get('verdict', '') and '미완' not in res.get('verdict', ''), res.get('verdict'))
    c('끝날 때 탭 1개', res.get('tabs_open_at_end') == 1, res.get('tabs_open_at_end'))
    c('결과 파일', (out / 'result.json').exists() and bool(rep))
    passed = sum(1 for x in checks if x['ok']); print(f'{who} {mode}: {passed}/{len(checks)}')
    for x in checks:
        if not x['ok']: print('  FAIL', x['check'], json.dumps(x['detail'], ensure_ascii=False)[:300])
    (HERE / 'evidence' / f'{who}_{mode}_qa.json').write_text(json.dumps({'passed': passed, 'total': len(checks), 'checks': checks, 'server': {k: st[k] for k in ('suggest', 'picks', 'edit_views', 'saves', 'orders', 'exports', 'display', 'display_views')} | {'downloads': len(st['downloads']), 'denied': len(st['denied'])}}, ensure_ascii=False, indent=1))
if __name__ == '__main__':
    main()
