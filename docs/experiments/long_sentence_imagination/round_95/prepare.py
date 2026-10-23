"""Synthetic fixtures and predetermined oracle, never supplied to the executor."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401
import datetime
import hashlib
import json
import os
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-23_95회차'
STATES = ['cancelled', 'execution_incomplete', 'missing', 'invalid',
          'stale', 'incompatible', 'blocked', 'verified']


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def snapshot(folder):
    return {str(p.relative_to(folder)): {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
            'mtime_ns': p.stat().st_mtime_ns} for p in folder.rglob('*') if p.is_file()}


def good(n):
    return {'job': f'J{n:02}', 'source_rev': 1, 'compat': n != 11,
            'items': [{'id': f'r{k:02}', 'amount': (k % 4 + 1) * (n * 10 + k)}
                      for k in range(1, 21)]}


def expected(phase):
    bad = ({4: 'execution_incomplete', 13: 'execution_incomplete', 5: 'missing',
            6: 'invalid', 7: 'invalid', 10: 'invalid', 12: 'invalid', 14: 'invalid',
            8: 'stale', 9: 'cancelled', 23: 'blocked', 24: 'blocked'} if phase == 1
           else {3: 'invalid', 9: 'cancelled', 11: 'incompatible'})
    rows = []
    for n in range(1, 25):
        status = bad.get(n, 'verified')
        attempt = 2 if n in (2, 13) else 1
        if phase == 2 and n in (4, 13, 9):
            attempt = {4: 2, 13: 3, 9: 9}[n]
        rows.append({'id': f'J{n:02}', 'status': status, 'attempt': attempt,
                     'total': sum(r['amount'] for r in good(n)['items']) if status == 'verified' else None})
    return {'phase': phase, 'release_ready': False, 'items': rows,
            'counts': {s: sum(r['status'] == s for r in rows) for s in STATES},
            'verified_total': sum(r['total'] or 0 for r in rows)}


def prepare():
    assert not OUT.exists(), 'never overwrite an existing rehearsal'
    for lane in ('trainer', 'ai'):
        base = OUT / lane / 'inputs'
        (OUT / lane / 'artifacts').mkdir(parents=True)
        jobs, receipts = [], []
        for n in range(1, 25):
            job = f'J{n:02}'
            jobs.append({'id': job, 'depends_on': ['J05'] if n == 23 else ['J23'] if n == 24 else []})
            source = {'job': job, 'rev': 1, 'items': [{'id': f'r{k:02}', 'qty': k % 4 + 1,
                      'price': n * 10 + k} for k in range(1, 21)]}
            dump(base / 'source' / f'{job}.json', source)
            artifact = good(n)
            if n == 7:
                artifact['items'][0]['amount'] += 1
            if n == 8:
                artifact['source_rev'] = 0
            if n == 10:
                artifact['items'][-1] = artifact['items'][0]
            if n == 12:
                artifact['job'] = 'J99'
            if n == 14:
                artifact['items'] = []
            if n != 5:
                dump(base / 'artifacts' / f'{job}.json', artifact)
            if n == 6:
                (base / 'artifacts' / f'{job}.json').write_text('{"job":"J06",')
            receipts.append({'job': job, 'attempt': 1, 'state': 'running' if n == 4 else 'succeeded'})
        receipts.insert(0, {'job': 'J02', 'attempt': 2, 'state': 'succeeded'})
        receipts.insert(0, {'job': 'J13', 'attempt': 2, 'state': 'failed'})
        receipts.extend([dict(receipts[1]), dict(receipts[-1])])
        dump(base / 'manifest.json', {'jobs': jobs})
        dump(base / 'receipts.json', {'items': receipts})
        dump(base / 'policy.json', {'cancelled': ['J09'], 'require_compat': False})
        (base / 'README.txt').write_text('旧 운영 안내: succeeded이면 인수 완료로 표시. 파일 존재만 검사. 호환성은 선택.\n')
        dump(OUT / 'runs' / f'{lane}_T1_inputs.json', snapshot(base))
    for phase in (1, 2):
        dump(OUT / 'reference' / f'T{phase}.json', expected(phase))
    dump(OUT / 'start.json', {'start': '2026-10-23T11:53:00+09:00',
         'deadline': '2026-10-23T12:53:00+09:00',
         'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()})
    shutil.copyfile('/tmp/l95_contracts.json', OUT / 'runs' / 'contracts.json')
    print(json.dumps({f'T{p}': expected(p)['counts'] for p in (1, 2)}, ensure_ascii=False))


def advance(lane):
    base = OUT / lane / 'inputs'
    assert not (OUT / 'runs' / f'{lane}_T2_inputs.json').exists()
    dump(OUT / 'runs' / f'{lane}_T1_outputs.json', snapshot(OUT / lane / 'artifacts'))
    dump(OUT / 'runs' / f'{lane}_T1_inputs_after.json', snapshot(base))
    for n in (5, 6, 7, 8, 10, 12, 14):
        dump(base / 'artifacts' / f'J{n:02}.json', good(n))
    receipts = json.loads((base / 'receipts.json').read_text())
    receipts['items'].extend([{'job': j, 'attempt': a, 'state': 'succeeded'}
                             for j, a in [('J04', 2), ('J13', 3), ('J09', 9)]])
    receipts['items'].reverse()
    dump(base / 'receipts.json', receipts)
    dump(base / 'policy.json', {'cancelled': ['J09'], 'require_compat': True})
    path = base / 'source/J03.json'
    before = path.stat()
    value = json.loads(path.read_text())
    value['items'][0]['price'] += 1
    dump(path, value)
    assert path.stat().st_size == before.st_size
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    dump(OUT / 'runs' / f'{lane}_T2_inputs.json', snapshot(base))
    print(lane, 'advanced; J03 same size and mtime, changed bytes')


if __name__ == '__main__':
    if sys.argv[1] == 'prepare':
        prepare()
    elif sys.argv[1] == 'advance':
        advance(sys.argv[2])
