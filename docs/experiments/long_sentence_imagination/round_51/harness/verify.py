"""결정론 검수 — 산출물 + 중앙 상주 원장 + 맥12(표식 R51= 프로세스·폴더). 사용: python3 verify.py <who> <mode>"""
import json, sys, time, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-11_51회차'
HERE = Path(__file__).resolve().parent.parent
DEV = 'guestpc-7a440e9daf61'
EXPECT = {'base': {'night': '끝남'}, 'b': {'night': '시간 초과로 끊김'}, 'c': {}, 'd': {'tidy': '끝남', 'index': '끝남'}}
def ibl(code):
    req = urllib.request.Request('http://127.0.0.1:8765/ibl/execute', data=json.dumps({'code': '#!ibl edition=2\n' + code, 'project_id': '수동모드', 'origin': 'training', 'task_id': 'r51-verify'}, ensure_ascii=False).encode(), headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(req, timeout=200))
def sh(cmd):
    v = ibl('return [limbs:guestpc]{op:"shell",limb:"%s",cmd:%s,cwd:"/tmp",mode:"observe",timeout:8}' % (DEV, json.dumps(cmd, ensure_ascii=False))).get('value') or {}
    return (v.get('result') or {}).get('output', '')
def main():
    who, mode = sys.argv[1], sys.argv[2]
    q = json.loads((OUT / '_oracle/expected.json').read_text())[f'{who}_{mode}']; out = OUT / who / mode / 'out'; exp = EXPECT[mode]
    ld = lambda n: json.loads((out / n).read_text()) if (out / n).exists() else {}
    ev, mo, rc = ld('evening.json'), ld('morning.json'), ld('receipt.json')
    mark = q['mark'].replace('R51=', 'R51[=]') + '-'
    left = [l for l in sh(f"ps -axo pid,etime,command | grep '{mark}' | cut -c1-150; true").split('\n') if l.strip()]
    disk = sh(f'ls -a "{q["remote_dir"]}" 2>&1 | head -6')
    h = ibl(f'return [limbs:guestpc]{{op:"history",limb:"{DEV}"}}').get('value') or {}
    key = rc.get('key') or f'r51-{who}_{mode}'
    mine = [t for t in h.get('tasks', []) if str(t.get('request_id', '')).startswith(key + '-') or any((q['remote_dir'] + e) in json.dumps(t.get('summary', {}), ensure_ascii=False) for e in ('"', '/', "'", '\\'))]
    night = [t for t in mine if 'sh jobs/night.sh' in str(t['summary'].get('cmd', ''))]
    checks = []
    def c(name, cond, detail=None): checks.append({'check': name, 'ok': bool(cond), 'detail': detail})
    b = ev.get('body', {})
    c('저녁: 문진 — 뚜껑 닫힘·어댑터·안 잠듦·화면 1대·못 본 항목 0', b.get('lid_closed') is True and b.get('power_source') == 'AC Power' and b.get('sleep_minutes') == 0 and b.get('displays') == 1 and b.get('not_seen') == [], {k: b.get(k) for k in ('lid_closed', 'power_source', 'sleep_minutes', 'displays', 'display_on', 'idle_seconds', 'free_gb', 'wifi_rssi', 'not_seen')})
    c('저녁: 시계 차이 ±2초 안', b.get('clock_diff_seconds') is not None and abs(b['clock_diff_seconds']) <= 2, b.get('clock_diff_seconds'))
    want_entrust = mode != 'c'
    c('저녁: 맡길지 판단과 근거', ev.get('decision', {}).get('entrust') is want_entrust and (want_entrust or len(rc.get('reasons', [])) == 2), rc.get('reasons'))
    c('원장: 밤일 접수 수 = 기대(다시 맡긴 것 없음)', len(night) == len(exp), [(t['request_id'], t['state']) for t in night])
    c('접수증: 작업 번호가 원장의 밤일과 같음', sorted(a.get('job_id') for a in rc.get('accepted', [])) == sorted(t['id'] for t in night), [a.get('job_id') for a in rc.get('accepted', [])])
    evrun = json.loads((OUT / 'runs' / f'{who}_{mode}_evening_v{"1" if mode == "d" else "0"}.json').read_text()) if who == 'trainer' else None
    if evrun and night: c('저녁 실행은 밤일이 끝나기 전에 끝남', all((t.get('ended_at') or 9e18) > evrun['ended'] or mode == 'b' for t in night), [round((t.get('ended_at') or 0) - evrun['ended'], 1) for t in night])
    c('원장: 깨우기 신호 0·화면 입력 0·sudo 0', all(t['summary'].get('op') not in ('wake', 'click', 'type', 'key', 'move', 'scroll', 'drag') and 'sudo' not in str(t['summary'].get('cmd', '')) for t in mine), sorted({t['summary'].get('op') for t in mine}))
    s = ev.get('sound', {})
    c('저녁: 소리 — 접수·멈춤·남은 재생 0·"소리 확인 안 됨"', s.get('accepted') is True and s.get('stopped') is True and s.get('processes_left') == 0 and s.get('audible_sound_verified') is False, {k: s.get(k) for k in ('accepted', 'running_seen', 'volume_zero_applied', 'stopped', 'processes_left')})
    sc = ev.get('screen', {})
    c('저녁: 화면 한 장의 결과와 읽기', bool(sc.get('reading')) and sc.get('input_events_sent') == 0, {k: sc.get(k) for k in ('captured', 'bytes', 'reading')})
    mj = {j['id']: j for j in mo.get('jobs', [])}
    c('아침: 일마다 종결이 기대와 같음', {k: v.get('outcome') for k, v in mj.items()} == exp, {k: v.get('outcome') for k, v in mj.items()})
    one = {str(t['summary']['cmd']).split(q['mark'] + '-')[1].split(' ')[0]: t for t in night}
    c('아침: 시작·종료·소요가 원장과 같음', all(k in one and v.get('seconds') is not None and abs(v['seconds'] - (one[k].get('seconds') or -9)) < 0.01 for k, v in mj.items()), {k: v.get('seconds') for k, v in mj.items()})
    okc = True; det = {}
    for jb in q['jobs']:
        if exp.get(jb['id']) == '끝남':
            p = out / Path(jb['result']).name; d = json.loads(p.read_text()) if p.exists() else {}; det[p.name] = d.get('beats'); okc = okc and d.get('beats') == jb['minutes'] * 12 and d.get('max_gap_s', 99) <= 15
        if exp.get(jb['id']) == '시간 초과로 끊김':
            p = out / Path(jb['partial']).name; n = len(p.read_text().split('\n')) - 1 if p.exists() else 0; det[p.name] = n; okc = okc and abs(n - jb['limit_s'] / 5) <= 2
    c('아침: 결과(끝난 일)·중간 기록(끊긴 일) 회수와 내용', okc and all(v.get('collected', {}).get('match') for v in mj.values()), det)
    if exp: c('아침: 잠들거나 멈춘 적 없음으로 판정', mo.get('slept_or_stalled') is False, mo.get('slept_or_stalled'))
    c('맥12: 표식 프로세스 0', not left, left[:4])
    c('맥12: 작업 폴더 없음', 'No such file' in disk, disk[:160])
    limb = [x for x in (ibl('return [self:limb]{op:"list"}').get('value') or {}).get('items', []) if x.get('device_id') == DEV]
    c('맥12 등록·연결 그대로', len(limb) == 1 and limb[0]['connected'] and (limb[0].get('registration') or {}).get('state') == 'active' and not limb[0]['registration'].get('paused'))
    passed = sum(1 for x in checks if x['ok']); print(f'{who} {mode}: {passed}/{len(checks)}  (원장 작업 {len(mine)}건, 밤일 {len(night)}건)')
    for x in checks:
        if not x['ok']: print('  FAIL', x['check'], json.dumps(x['detail'], ensure_ascii=False)[:380])
    row = lambda t: {'id': t['id'], 'request_id': t['request_id'], 'state': t['state'], 'op': t['summary'].get('op'), 'mode': t['summary'].get('mode'), 'cmd': str(t['summary'].get('cmd', ''))[:80], 'created': t['created'], 'started_at': t.get('started_at'), 'ended_at': t.get('ended_at'), 'seconds': t.get('seconds')}
    (HERE / 'evidence' / f'{who}_{mode}_qa.json').write_text(json.dumps({'passed': passed, 'total': len(checks), 'checks': checks, 'ledger': [row(t) for t in sorted(mine, key=lambda t: t['created'])], 'left': left, 'disk': disk}, ensure_ascii=False, indent=1))
if __name__ == '__main__':
    main()
