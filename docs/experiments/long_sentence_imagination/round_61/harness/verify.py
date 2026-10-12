"""Independent oracle: reconstruct from only the available input files."""
import argparse
import html
import re
import json
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-12_61회차'

def norm(s): return unicodedata.normalize('NFC',s)
def key(r): return (norm(r['sku']),norm(r['warehouse']))
def expected(source):
    files=json.loads((source/'manifest.json').read_text())['files']
    stock=json.loads((source/'stock.json').read_text())
    raw=[]; failed=[]
    for name in files:
        if not (source/name).exists(): failed.append(name)
        else: raw+=json.loads((source/name).read_text())
    latest={}
    for e in raw:
        if e['id'] not in latest or latest[e['id']]['version']<e['version']: latest[e['id']]=e
    groups={}
    for e in latest.values():
        g=groups.setdefault(key(e),dict(known=0,missing=0,ids=[]))
        g['ids'].append(e['id'])
        if e['qty'] is None: g['missing']+=1
        else: g['known']+=(-1 if e['kind']=='출고' else 1)*e['qty']
    rows=[]
    for r in stock:
        g=groups.get(key(r),dict(known=0,missing=0,ids=[]))
        total=None if failed or g['missing'] else r['opening']+g['known']
        diff=None if total is None else r['counted']-total
        rows.append({**r,**g,'expected':total,'difference':diff,'status':'미확인' if diff is None else '차이' if diff else '일치'})
    counts=Counter(r['status'] for r in rows)
    stock_keys={key(r) for r in stock}
    unknown=[e for e in latest.values() if e['qty'] is None]
    return dict(summary=dict(raw=len(raw),unique=len(latest),excluded=len(raw)-len(latest),matched=counts['일치'],different=counts['차이'],unknown=counts['미확인']),rows=rows,unknown_events=unknown,unregistered=[{'sku':k[0],'warehouse':k[1],**v} for k,v in groups.items() if k not in stock_keys],failed_sources=failed)

def verify(source, target):
    want=expected(source); got=json.loads((target/'result.json').read_text()); report=(target/'report.md').read_text(); readable=html.unescape(report.replace('\\|','|').replace('<br>','\n'))
    failures=[]
    def check(ok,msg):
        if not ok: failures.append(msg)
    check(got['summary']==want['summary'], f"summary: {got['summary']} != {want['summary']}")
    actual={key(r):r for r in got['rows']}
    check(len(actual)==len(want['rows'])==len(got['rows']),'row keys/count')
    for r in want['rows']:
        a=actual.get(key(r),{})
        for field in ['opening','counted','known','missing','expected','difference','status']:
            check(a.get(field)==r[field],f'{key(r)} {field}: {a.get(field)} != {r[field]}')
        check(sorted(a.get('ids',[]))==sorted(r['ids']), f'{key(r)} evidence ids')
        check(r['sku'] in readable and r['warehouse'] in norm(readable),f'{key(r)} report row')
    check(sorted(e['id'] for e in got['unknown_events'])==sorted(e['id'] for e in want['unknown_events']),'unknown events')
    check({key(r) for r in got['unregistered']}=={key(r) for r in want['unregistered']},'unregistered keys')
    check(sorted(r['name'] for r in got['failed_sources'])==want['failed_sources'],'failed sources')
    # Verify table geometry as well as numeric JSON; raw pipes in names must not create columns.
    table_lines=[line for line in report.splitlines() if line.startswith('|')]
    detail=[line for line in table_lines if html.unescape(re.split(r'(?<!\\)\|',line)[1].strip().replace('\\|','|')) in {r['sku'] for r in want['rows']}]
    for line in detail:
        cells=re.split(r'(?<!\\)\|',line)[1:-1]
        check(len(cells) in (8,10), 'report column count: '+line[:90])
        cells=[html.unescape(c.strip().replace('\\|','|').replace('<br>','\n')) for c in cells]
        ref=next((r for r in want['rows'] if key(r)==(norm(cells[0]),norm(cells[1]))),None)
        check(ref is not None, 'report row identity: '+line[:90])
        if ref and len(cells) in (8,10):
            expected_cells=[str(ref[f]) if ref[f] is not None else '미확인' for f in ['opening','known','counted','expected','difference','status']]
            actual_cells=['미확인' if c=='null' else c for c in cells[2:8]]
            check(actual_cells==expected_cells, 'report values: '+line[:90])
    check(len(detail)==len(want['rows']),'report detail row count')
    actual_extra={key(r):r for r in got['unregistered']}
    for r in want['unregistered']:
        a=actual_extra.get(key(r),{})
        for field in ['known','missing']:
            check(a.get(field)==r[field],f'unregistered {key(r)} {field}')
        check(sorted(a.get('ids',[]))==sorted(r['ids']),f'unregistered {key(r)} evidence ids')
    return {'passed':not failures,'checks':f"summary + {len(want['rows'])} rows × 8 fields + evidence IDs + report cells + exceptions",'failure_count':len(failures),'failures':failures,'expected_summary':want['summary']}

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('who'); p.add_argument('case'); p.add_argument('--out'); a=p.parse_args()
    result=verify(OUT/a.who/a.case/'input',Path(a.out) if a.out else OUT/a.who/a.case/'out')
    dest=OUT/'runs'/f'verify_{a.who}_{a.case}.json'; dest.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False)[:6000])
