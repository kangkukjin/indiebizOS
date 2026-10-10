"""결정론 검수 — 산출물 + 중앙 상주 원장(history: 시작·종료 구간) + 맥12 의 ps(표식 R50=) + 안전망. 사용: python3 verify.py <who> <mode> [--suffix S]
안전망: 표식 프로세스가 남아 있으면 무엇이 남았는지 기록한 뒤 내린다(검수는 '내리기 전에 0 이었나')."""
import json, sys, time, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-10_50회차'
HERE = Path(__file__).resolve().parent.parent
DEV = 'guestpc-7a440e9daf61'
STATE = {'성공': 'succeeded', '실패': 'failed', '내가 멈춤': 'cancelled'}
def ibl(code):
    req = urllib.request.Request('http://127.0.0.1:8765/ibl/execute', data=json.dumps({'code': '#!ibl edition=2\n' + code, 'project_id': '수동모드', 'origin': 'training', 'task_id': 'r50-verify'}, ensure_ascii=False).encode(), headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(req, timeout=200))
def sh(cmd, tag):
    v = ibl('return [limbs:guestpc]{op:"shell",limb:"%s",cmd:%s,cwd:"/tmp",request_id:"r50-verify-%s-%d"}' % (DEV, json.dumps(cmd, ensure_ascii=False), tag, time.time() * 10)).get('value') or {}
    return (v.get('result') or {}).get('output', '')
def ledger(pred):
    tasks = []; cur = None
    h = ibl(f'return [limbs:guestpc]{{op:"history",limb:"{DEV}"}}').get('value') or {}
    return [t for t in h.get('tasks', []) if pred(t)]
def main():
    who, mode = sys.argv[1], sys.argv[2]; suffix = sys.argv[sys.argv.index('--suffix') + 1] if '--suffix' in sys.argv else ''
    e = json.loads((OUT / '_oracle/expected.json').read_text())[f'{who}_{mode}']; q = e['queue']; exp = e['expect']; out = OUT / who / mode / 'out'
    res = json.loads((out / 'result.json').read_text()) if (out / 'result.json').exists() else {}; rep = (out / 'report.md').read_text() if (out / 'report.md').exists() else ''
    mark = q['mark'].replace('R50=', 'R50[=]') + '-'
    left = [l for l in sh(f"ps -axo pid,ppid,etime,command | grep '{mark}' | cut -c1-170; true", 'ps').split('\n') if l.strip()]
    if left: sh(f"pkill -9 -f '{mark}'; true", 'net')
    disk = sh(f'ls -d "{q["remote_dir"]}" 2>&1; ls /Users/kangkukjin/indiebiz-training/r50 2>&1', 'ls')
    mine = ledger(lambda t: q['remote_dir'] in json.dumps(t.get('summary', {}), ensure_ascii=False) and q['mark'] + '-' in str(t['summary'].get('cmd', '')) and 'sh jobs/' in str(t['summary'].get('cmd', '')))
    by = {}
    for t in mine:
        jid = str(t['summary']['cmd']).split(q['mark'] + '-')[1].split(' ')[0]; by.setdefault(jid, []).append(t)
    checks = []
    def c(name, cond, detail=None): checks.append({'check': name, 'ok': bool(cond), 'detail': detail})
    rj = {r['id']: r for r in res.get('jobs', [])} if isinstance(res.get('jobs'), list) else {}
    c('보고: 일마다 종결이 기대와 같음', {k: (rj.get(k) or {}).get('outcome') for k in exp} == exp, {k: (rj.get(k) or {}).get('outcome') for k in exp})
    c('원장: 일마다 실행 1번(맡기지 않을 일은 0번)', all(len(by.get(k, [])) == (0 if v == '맡기지 않음' else 1) for k, v in exp.items()), {k: len(v) for k, v in by.items()})
    one = {k: v[0] for k, v in by.items()}
    c('원장: 상태가 종결과 맞음', all(one[k]['state'] == STATE[v] for k, v in exp.items() if v in STATE and k in one), {k: (t['state'], (t.get('result') or {}).get('exit'), (t.get('result') or {}).get('timeout')) for k, t in one.items()})
    cut = [k for k, v in exp.items() if v == '시간 초과로 끊김']
    lim = {j['id']: j.get('limit_s') for j in q['jobs']}; stop = {j['id']: j.get('stop_after_s') for j in q['jobs']}; after = {j['id']: j.get('after') for j in q['jobs']}
    c('원장: 끊긴 일은 제한시간 근처에서 끝남', all(k in one and one[k].get('seconds') is not None and lim[k] - 2 <= one[k]['seconds'] <= lim[k] + 8 for k in cut), {k: (one.get(k) or {}).get('seconds') for k in cut})
    st = [k for k, v in exp.items() if v == '내가 멈춤']
    c('원장: 멈춘 일은 지시한 때 근처에서 끝남', all(k in one and one[k].get('seconds') is not None and stop[k] - 1 <= one[k]['seconds'] <= stop[k] + 14 for k in st), {k: (one.get(k) or {}).get('seconds') for k in st})
    iv = sorted((t['started_at'], t['ended_at']) for t in one.values() if t.get('started_at') and t.get('ended_at'))
    peak = max((sum(1 for a, b in iv if a <= s < b) for s, _ in iv), default=0)
    c('원장: 동시에 돈 일이 한도 2 를 넘지 않음', len(iv) == len(one) and peak <= 2, {'peak': peak, 'timed': len(iv), 'tasks': len(one)})
    dep = [(k, a) for k, a in after.items() if a and k in one]
    c('원장: 뒤 일은 앞 일이 끝난 뒤에 접수됨', all(a in one and one[a].get('ended_at') and one[k]['created'] >= one[a]['ended_at'] - 0.5 for k, a in dep), [(k, a, round(one[k]['created'] - (one[a].get('ended_at') or 0), 1)) for k, a in dep if a in one])
    c('보고: 시작·종료·소요·줄 대기가 원장 값과 같음("시각 없음" 0)', all(k in rj and rj[k].get('seconds') is not None and abs(rj[k]['seconds'] - (t.get('seconds') or -9)) < 0.01 and rj[k].get('waited') is not None for k, t in one.items()), {k: (rj.get(k) or {}).get('seconds') for k in one})
    soc = {r['id']: r for r in res.get('stopped_or_cut', [])} if isinstance(res.get('stopped_or_cut'), list) else {}
    c('보고: 멈춘·끊긴 일의 남은 프로세스 확인 기록', sorted(soc) == sorted(st + cut), {k: v.get('left') for k, v in soc.items()})
    ka = [j for j in q['jobs'] if j.get('keep_alive')]; rk = {r['id']: r for r in res.get('keep_alive', [])} if isinstance(res.get('keep_alive'), list) else {}
    c('보고: 서버 생존·내용 확인', all(j['id'] in rk and rk[j['id']].get('alive') is True and rk[j['id']].get('content_ok') is True for j in ka), {k: (v.get('alive'), v.get('content_ok'), v.get('body')) for k, v in rk.items()})
    c('맥12: 끝난 뒤 표식 프로세스 0 (안전망이 치우기 전)', not left, left[:6])
    c('맥12: 작업 폴더 없음', 'No such file' in disk.split('\n')[0], disk[:200])
    want = [j for j in q['jobs'] if j.get('result') and exp[j['id']] == '성공']
    okf = True; det = {}
    for j in want:
        p = out / Path(j['result']).name; det[p.name] = p.exists(); okf = okf and p.exists()
    if (out / 'sum.json').exists(): det['total'] = json.loads((out / 'sum.json').read_text()).get('total'); okf = okf and det['total'] == 1301160
    c('회수: 성공한 일의 결과 파일(내용까지)', okf and all(r.get('match') for r in res.get('collected', [])) and len(res.get('collected', [])) == len(want), det)
    limb = [x for x in (ibl('return [self:limb]{op:"list"}').get('value') or {}).get('items', []) if x.get('device_id') == DEV]
    c('맥12 등록·연결 그대로', len(limb) == 1 and limb[0]['connected'] and (limb[0].get('registration') or {}).get('state') == 'active' and not limb[0]['registration'].get('paused'))
    allmine = ledger(lambda t: str(t.get('request_id', '')).startswith(res.get('key') or '\x00') or q['remote_dir'] in json.dumps(t.get('summary', {}), ensure_ascii=False))
    c('원장: sudo·화면·재생·훈련 폴더 밖 0', all(t['summary'].get('op') in ('shell', 'transfer', 'info', 'list') and 'sudo' not in str(t['summary'].get('cmd', '')) for t in allmine), sorted({t['summary'].get('op') for t in allmine}))
    c('결과 파일', bool(res) and '판정' in rep)
    prev = HERE / 'evidence' / f'{who}_{mode}_qa.json'
    if suffix and prev.exists():
        old = {x['id'] for x in json.loads(prev.read_text())['ledger_all']}; new = [t for t in allmine if t['id'] not in old and not str(t['request_id']).startswith('r50-verify')]
        c('재부탁: 원장에 새 작업 0', not new, [(t['summary'].get('op'), t['request_id'][:40]) for t in new])
    passed = sum(1 for x in checks if x['ok']); print(f'{who} {mode}{suffix}: {passed}/{len(checks)}  (일 작업 {len(mine)}건, 동시 최대 {peak})')
    for x in checks:
        if not x['ok']: print('  FAIL', x['check'], json.dumps(x['detail'], ensure_ascii=False)[:420])
    row = lambda t: {'id': t['id'], 'request_id': t['request_id'], 'state': t['state'], 'op': t['summary'].get('op'), 'cmd': str(t['summary'].get('cmd', ''))[:90], 'created': t['created'], 'started_at': t.get('started_at'), 'ended_at': t.get('ended_at'), 'seconds': t.get('seconds'), 'result': {k: v for k, v in (t.get('result') or {}).items() if k != 'output'}}
    (HERE / 'evidence' / f'{who}_{mode}{suffix}_qa.json').write_text(json.dumps({'passed': passed, 'total': len(checks), 'checks': checks, 'ledger_jobs': [row(t) for t in mine], 'ledger_all': [row(t) for t in allmine], 'left_before_net': left, 'disk': disk}, ensure_ascii=False, indent=1))
if __name__ == '__main__':
    main()
