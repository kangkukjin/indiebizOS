"""결정론 검수 — 산출물(result.json·report.md·summary_mobile.png) + 서버 state(진짜 저장) + oracle. 사용: verify.py <who> <mode> [--site-key KEY]"""
import json, struct, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-09_47회차'
HERE = Path(__file__).resolve().parent.parent
def main():
    who, mode = sys.argv[1], sys.argv[2]
    sub = {'base': 'out', 'flaky': 'out_flaky', 'b': 'out_b'}[mode]; key = who + {'base': '', 'flaky': '_flaky', 'b': '_b'}[mode]
    if '--out' in sys.argv: sub = sys.argv[sys.argv.index('--out') + 1]
    if '--site-key' in sys.argv: key = sys.argv[sys.argv.index('--site-key') + 1]
    exp = json.loads((OUT / '_oracle/expected.json').read_text()); st = json.loads((OUT / '_site' / f'{key}.json').read_text())
    out = OUT / who / sub; res = json.loads((out / 'result.json').read_text()); rep = (out / 'report.md').read_text() if (out / 'report.md').exists() else ''
    pol = exp['policy_b'] if mode == 'b' else exp['policy']; late = sorted(exp['late']); locked = exp['locked'] if mode == 'flaky' else None
    want_flags = sorted(k for k, v in exp['late'].items() if v >= pol['flag_min_qty']); want_moved = [i for i in late if i != locked]
    ok_moves = sorted(m['id'] for m in st['moves'] if m['ok']); stray = sorted(set(m['id'] for m in st['moves']) - set(late))
    fin = st['final']; checks = []
    def c(name, cond, detail=None): checks.append({'check': name, 'ok': bool(cond), 'detail': detail})
    by = {r.get('status'): r.get('n') for r in res.get('by_status', [])}
    c('목록 40건 전부 읽음', res.get('total') == 40 and st['api_orders'] == [12, 24, 36], {'total': res.get('total'), 'api': st['api_orders']})
    c('상태별 건수', by == {k: v for k, v in exp['counts_before'].items() if v}, by)
    c('지연 5건 식별', sorted(r['id'] for r in res.get('late', [])) == late)
    c('지연만 보기 사용', st['late_views'] >= 1, st['late_views'])
    c('서버: 대상 카드만 이동(다른 카드 0)', not stray, stray)
    c('서버: 이동 저장', ok_moves == want_moved and all(fin[i]['status'] == pol['to'] for i in want_moved), ok_moves)
    c('서버: 메모 저장', all(fin[i]['memo'] == pol['memo'] for i in late), {i: fin[i]['memo'] for i in late})
    c('서버: 우선 표시 정확', sorted(i for i in fin if fin[i]['flag']) == want_flags, sorted(i for i in fin if fin[i]['flag']))
    c('보고: 저장 안 된 카드', sorted(res.get('not_moved', [])) == ([locked] if locked else []), res.get('not_moved'))
    if locked:
        c('보고: 화면만 옮겨짐을 구별', sorted(res.get('ui_only', [])) == [locked], res.get('ui_only'))
        c('보고: 판정이 완료가 아님', '완료' not in res.get('verdict', '').split('—')[0] and locked in rep, res.get('verdict'))
        c('콘솔 오류로 실패 근거', any(locked in e for e in res.get('console', {}).get('errors', [])), res.get('console', {}).get('errors'))
    else:
        c('보고: 판정 완료', '완료' in res.get('verdict', ''), res.get('verdict'))
    net = res.get('network', {})
    c('네트워크 기록 정직 보고', net.get('capturing') is True or ('못' in net.get('note', '') or '미확인' in net.get('note', '') or '없' in net.get('note', '')), net)
    c('콘솔 경고 보고', any(exp['console_warning'] in w for w in res.get('console', {}).get('warnings', [])), res.get('console', {}).get('warnings'))
    sm = res.get('summary', {}); png = out / 'summary_mobile.png'; w = h = None
    if png.exists():
        b = png.read_bytes()[:24]; w, h = struct.unpack('>II', b[16:24])
    c('요약 휴대폰 폭 스크린샷', png.exists() and w == 390, {'w': w, 'h': h})
    c('요약 모바일 배치 읽음·대조', sm.get('mobile_layout') is True and sm.get('all_match') is True, {'mobile': sm.get('mobile_layout'), 'match': sm.get('all_match')})
    srv_counts = st['counts']; c('요약 숫자 = 서버', {r['name']: r['summary'] for r in sm.get('rows', []) if r['name'] in srv_counts} == srv_counts, srv_counts)
    ss = res.get('session', {})
    c('로그인 1회·새 브라우저 복원', st['logins'] == 1 and ss.get('restored') is True and 'login' in str(ss.get('new_browser_first_url')), {'logins': st['logins'], **ss})
    c('복원 뒤 재확인 일치', ss.get('recheck_match') is True)
    c('결과 파일', (out / 'result.json').exists() and bool(rep))
    passed = sum(1 for x in checks if x['ok']); print(f'{who} {mode}: {passed}/{len(checks)}')
    for x in checks:
        if not x['ok']: print('  FAIL', x['check'], json.dumps(x['detail'], ensure_ascii=False)[:300])
    (HERE / 'evidence' / f'{who}_{mode}_qa.json').write_text(json.dumps({'passed': passed, 'total': len(checks), 'checks': checks, 'server': {k: st[k] for k in ('logins', 'moves', 'memos', 'flags', 'counts', 'board_views', 'late_views', 'summary_views', 'api_orders')}}, ensure_ascii=False, indent=1))
if __name__ == '__main__':
    main()
