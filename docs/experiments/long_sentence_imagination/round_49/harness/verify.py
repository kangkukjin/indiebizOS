"""결정론 검수 — 산출물 + 중앙 원본 지문 + 중앙 상주 원장(history) + 맥12 디스크(검증 셸, 요청ID r49-verify-*). 사용: .venv/bin/python3 verify.py <who> <mode> [--suffix S]"""
import hashlib, io, json, sys, time, unicodedata, urllib.request, zipfile
from pathlib import Path
from PIL import Image
ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-10_49회차'
HERE = Path(__file__).resolve().parent.parent
DEV = 'guestpc-7a440e9daf61'
nfc = lambda s: unicodedata.normalize('NFC', s)
def ibl(code):
    req = urllib.request.Request('http://127.0.0.1:8765/ibl/execute', data=json.dumps({'code': '#!ibl edition=2\n' + code, 'project_id': '수동모드', 'origin': 'training', 'task_id': 'r49-verify'}, ensure_ascii=False).encode(), headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(req, timeout=200))
def main():
    who, mode = sys.argv[1], sys.argv[2]; suffix = sys.argv[sys.argv.index('--suffix') + 1] if '--suffix' in sys.argv else ''
    exp = json.loads((OUT / '_oracle/expected.json').read_text())[f'{who}_{mode}']; job = exp['job']; out = OUT / who / mode / 'out'
    res = json.loads((out / 'result.json').read_text()) if (out / 'result.json').exists() else {}; rep = (out / 'report.md').read_text() if (out / 'report.md').exists() else ''
    checks = []
    def c(name, cond, detail=None): checks.append({'check': name, 'ok': bool(cond), 'detail': detail})
    txt = json.dumps(res, ensure_ascii=False)
    # 원장: 이 실행 폴더를 cwd·경로로 가진 작업들
    h = ibl(f'return [limbs:guestpc]{{op:"history",limb:"{DEV}"}}').get('value') or {}
    key = res.get('key') or '\x00'
    mine = [t for t in h.get('tasks', []) if (str(t.get('request_id', '')).startswith(key) or job['remote_dir'] in json.dumps(t.get('summary', {}), ensure_ascii=False)) and not str(t.get('request_id', '')).startswith('r49-verify')]
    mine = [t for t in mine if str(t.get('request_id', '')).startswith(key)] or mine
    conv = [t for t in mine if 'sh convert.sh' in str(t['summary'].get('cmd', ''))]
    # 맥12 디스크
    v = ibl(f'return [limbs:guestpc]{{op:"shell",limb:"{DEV}",cmd:"ls -a \\"{job["remote_dir"]}\\" 2>&1 | head -5; echo ---; ls /Users/kangkukjin/indiebiz-training/r49 2>&1",cwd:"/tmp",request_id:"r49-verify-{who}-{mode}-{int(time.time())}"}}').get('value') or {}
    disk = (v.get('result') or {}).get('output', '')
    limb = [x for x in (ibl('return [self:limb]{op:"list"}').get('value') or {}).get('items', []) if x.get('device_id') == DEV]
    stage = out / '_stage/photos.zip'
    c('보낸 묶음 지문 = 중앙 묶음(보고값·실파일)', stage.exists() and res.get('sent', {}).get('remote_sha256') == hashlib.sha256(stage.read_bytes()).hexdigest(), res.get('sent', {}).get('remote_sha256'))
    c('원본 지문 대조 전건(이름 누락 0)', res.get('originals', {}).get('match') is True and res['originals'].get('remote_listed') == len(exp['files']) and not res['originals'].get('name_missing') and not res['originals'].get('changed'), res.get('originals'))
    names = sorted(nfc(n[:-4]) for n, f in exp['files'].items() if n not in exp['skipped'] and n not in exp['broken'])
    zs = [p for p in out.glob('*.zip')]; zp = out / (job['bundle'] + '.zip')
    got = []; bad = []
    if zp.exists():
        with zipfile.ZipFile(zp) as z:
            for i in z.infolist():
                if i.is_dir(): continue
                im = Image.open(io.BytesIO(z.read(i))); got.append(nfc(Path(i.filename).stem))
                if max(im.size) > job['long_side'] or im.format != 'JPEG': bad.append([i.filename, im.size, im.format])
    c('회수 묶음: 기대 사진 전부·그것만(이름이 읽히는 글자)', sorted(got) == names, {'got': len(got), 'want': len(names), 'sample': got[:2], 'zips': [p.name for p in zs]})
    c('회수 사진 전부 JPEG·긴 변 규격(중앙에서 직접 엶)', zp.exists() and not bad, bad[:3])
    c('회수 묶음·로그 지문 = 보고된 원격 지문', zp.exists() and (out / 'convert.log').exists() and hashlib.sha256(zp.read_bytes()).hexdigest() == res.get('collect', {}).get('zip', {}).get('remote_sha256') and hashlib.sha256((out / 'convert.log').read_bytes()).hexdigest() == res['collect']['log'].get('remote_sha256'))
    c('원장: 변환 작업 1건(중복 실행 없음)', len(conv) == 1, [(t['request_id'], t['state']) for t in conv])
    c('보고: 원격 실행 횟수 1(runs.log)', res.get('convert', {}).get('remote_runs') == 1, res.get('convert', {}).get('remote_runs'))
    lay = res.get('convert', {}).get('layers', {})
    if exp['broken']:
        c('원장: 변환 상태 failed·종료 3', conv and conv[0]['state'] == 'failed' and (conv[0].get('result') or {}).get('exit') == 3, [(t['state'], (t.get('result') or {}).get('exit')) for t in conv])
        c('보고: 층 구분(상태 failed·종료 3·검사 통과·회수)', lay.get('state') == 'failed' and lay.get('exit') == 3 and lay.get('inspected') is True and lay.get('collected') is True, lay)
        c('보고: 깨진 사진과 실패 원문', sorted(nfc(x) for x in res['convert'].get('failed', [])) == sorted(exp['broken']) and len(res['convert'].get('failure_text', [])) >= 1, res['convert'].get('failed'))
        c('보고: 판정 부분 완료', '부분 완료' in res.get('verdict', ''), res.get('verdict'))
    else:
        c('원장: 변환 상태 succeeded·종료 0', conv and conv[0]['state'] == 'succeeded' and (conv[0].get('result') or {}).get('exit') == 0, [(t['state'], (t.get('result') or {}).get('exit')) for t in conv])
        c('보고: 층 구분(접수·상태·종료·검사·회수)', lay == {'accepted': True, 'state': 'succeeded', 'exit': 0, 'command_ok': True, 'inspected': True, 'collected': True}, lay)
        c('보고: 판정 완료', res.get('verdict', '').startswith('완료'), res.get('verdict'))
    c('보고: 건너뛴 사진 = 제외 규칙', sorted(nfc(x) for x in res.get('convert', {}).get('skipped', [])) == sorted(exp['skipped']), res.get('convert', {}).get('skipped'))
    hist = res.get('history', [])
    led = {t['id']: t for t in mine}
    c('보고: 작업별 시작·종료·소요가 원장과 같음', len(hist) >= 5 and all(r.get('seconds') is not None and r.get('job') in led and r.get('state') == led[r['job']]['state'] for r in hist), [(r.get('name'), r.get('state'), r.get('seconds')) for r in hist])
    c('두 작업의 폴더·환경 분리 확인', res.get('isolation', {}).get('separate') is True, res.get('isolation'))
    c('맥12 디스크: 작업 폴더 없음', 'No such file' in disk.split('---')[0], disk[:300])
    c('맥12 등록·연결 그대로', len(limb) == 1 and limb[0]['connected'] and not limb[0]['revoked'] and (limb[0].get('registration') or {}).get('state') == 'active' and not limb[0]['registration'].get('paused'))
    c('원장: 훈련 폴더 밖 경로·sudo·화면·재생 0', all(t['summary'].get('op') in ('shell', 'transfer', 'info', 'list') and 'sudo' not in str(t['summary'].get('cmd', '')) for t in mine), sorted({t['summary'].get('op') for t in mine}))
    c('결과 파일', bool(res) and bool(rep) and '판정' in rep)
    passed = sum(1 for x in checks if x['ok']); print(f'{who} {mode}{suffix}: {passed}/{len(checks)}  (원장 작업 {len(mine)}건, 변환 {len(conv)}건)')
    for x in checks:
        if not x['ok']: print('  FAIL', x['check'], json.dumps(x['detail'], ensure_ascii=False)[:400])
    (HERE / 'evidence' / f'{who}_{mode}{suffix}_qa.json').write_text(json.dumps({'passed': passed, 'total': len(checks), 'checks': checks, 'ledger': [{'id': t['id'], 'request_id': t['request_id'], 'state': t['state'], 'op': t['summary'].get('op'), 'created': t['created']} for t in mine], 'disk': disk}, ensure_ascii=False, indent=1))
if __name__ == '__main__':
    main()
