"""Synthetic inputs and independent expected values; no task implementation."""
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
DOC = ROOT / 'docs/experiments/long_sentence_imagination/round_59'
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-12_59회차'

def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2))

def prepare():
    seed = OUT / 'seed'
    rows = []
    for level in range(5):
        for i in range(40):
            name = f'공통 {i}.html' if i < 4 else f'문서 {level}-{i:02}.html'
            rel = '자료/' + name
            source = f'{level}/{rel}'
            # Five links per document: same visible low-level targets, plus one missing edge.
            targets = [f'자료/공통 {j}.html' for j in range(4)] + ['자료/문서 0-39.html']
            if level == 4 and i == 39:
                targets[-1] = '자료/없는 파일.html'
            body = '<!doctype html><html><meta charset="utf-8"><title>' + name + '</title><body>'
            body += f'<h1>{name}</h1><p>등급 {level} 문서 {i}, 버전 1</p>'
            body += ''.join(f'<a href="{t.split("/",1)[1]}">참조</a>' for t in targets) + '</body></html>\r\n'
            if i == 31:
                body = '<html><body>동일 자료</body></html>\r\n'
            path = seed / 'warehouse' / source
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body.encode())
            rows.append({'source':source,'relative':rel,'level':level,
                         'managed': i >= 8, 'desired_level':2 if level == 0 and 10 <= i < 20 else level,
                         'version':None if i == 30 else 1, 'expected_links':len(targets) if i != 31 else 0})
    # 975 actual HTML edges (five duplicate-content pages have no links).
    # 25 .url edges add 25 files: total 225 files and 1000 source links.
    for i in range(25):
        source=f'0/추천/추천 {i}.url'
        body=f'[InternetShortcut]\nURL=https://example.invalid/reference/{i}\n'
        path=seed/'warehouse'/source;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(body)
        rows.append({'source':source,'relative':source[2:],'level':0,'managed':False,'desired_level':0,'version':1,'expected_links':1})
    # One planned destination is occupied with unrelated data: must hold, never rename silently.
    collision='2/자료/문서 0-19.html'
    p=seed/'warehouse'/collision;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('수동으로 놓은 동명 자료\n')
    rows.append({'source':collision,'relative':collision[2:],'level':2,'managed':False,'desired_level':2,'version':1,'expected_links':0})
    policy={'items':rows,'rules':{'manual':'preserve bytes and location','unknown_version':'hold',
        'move':'managed and known-version; retain relative path; destination conflict must hold',
        'duplicate':'report equal bytes; do not delete because level/link semantics may differ',
        'external_url':'record only, do not contact external service'}}
    dump(seed/'policy.json',policy)
    initial={r['source']:hashlib.sha256((seed/'warehouse'/r['source']).read_bytes()).hexdigest() for r in rows}
    expected=dict(initial)
    moves=[]
    for r in rows:
        if r['managed'] and r['version'] is not None and r['desired_level'] != r['level']:
            dest=str(r['desired_level'])+'/'+r['relative']
            if dest in initial: continue
            expected[dest]=expected.pop(r['source']);moves.append({'source':r['source'],'dest':dest})
    dump(OUT/'oracle.json',{'initial':initial,'expected':expected,'moves':moves,'count':len(rows),'link_count':1000})
    for name in ('trainer','variant','ai'):
        shutil.copytree(seed,OUT/name,dirs_exist_ok=True)
    dump(OUT/'started.json',{'started':datetime.now(timezone.utc).isoformat(),'limit_minutes':60,'revision':'1d2efc1c'})
    print(json.dumps({'files':len(rows),'moves':len(moves),'held_conflicts':1,'links':1000}))

if __name__=='__main__': prepare()
