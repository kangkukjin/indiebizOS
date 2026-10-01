"""Deterministic synthetic inventory; independent SQLite oracle and artifact validation."""
import csv
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
WORK = ROOT / 'outputs/long_sentence_imagination/2026-10-01_16회차'
HERE = Path(__file__).resolve().parent


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def generate():
    folder = WORK / 'input'
    folder.mkdir(parents=True, exist_ok=True)
    catalog = [dict(sku=f'S{s:03}', pack=[6, 8, 10, 12][s % 4], threshold=60+s*7 % 70)
               for s in range(1, 81)]
    opening = [dict(warehouse=f'W{w}', sku=f'S{s:03}', opening=45+((w-1)*80+s)*13 % 110)
               for w in range(1, 5) for s in range(1, 81)]
    movements = [dict(id=f'M{i+1:04}', warehouse=opening[i % 320]['warehouse'],
                      sku=opening[i % 320]['sku'], delta=i*7 % 31-20) for i in range(3200)]
    reserves = [dict(id=f'R{i+1:04}', warehouse=opening[i % 320]['warehouse'],
                     sku=opening[i % 320]['sku'], qty=1+i*3 % 13,
                     status='cancelled' if i % 5 == 0 else 'active') for i in range(480)]
    dump(folder / 'catalog.json', catalog)
    dump(folder / 'opening.json', opening)
    for n in range(4):
        rows = movements[n*800:(n+1)*800] + movements[n*800:n*800+4]
        write_csv(folder / f'movements_{n+1}.csv', rows)
    write_csv(folder / 'reservations.csv', reserves)
    for offset in (0, 20):
        dump(HERE / f'expected_{offset}.json', oracle(offset))


def write_csv(path, rows):
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, list(rows[0])); writer.writeheader(); writer.writerows(rows)


def oracle(offset):
    folder = WORK / 'input'
    db = sqlite3.connect(':memory:'); db.row_factory = sqlite3.Row
    db.executescript('CREATE TABLE catalog(sku,pack INT,threshold INT);'
                     'CREATE TABLE opening(warehouse,sku,opening INT);'
                     'CREATE TABLE movement(id,warehouse,sku,delta INT);'
                     'CREATE TABLE reservation(id,warehouse,sku,qty INT,status);')
    for name in ('catalog', 'opening'):
        rows = json.loads((folder / f'{name}.json').read_text())
        db.executemany(f'INSERT INTO {name} VALUES (?,?,?)', [tuple(r.values()) for r in rows])
    for path in sorted(folder.glob('movements_*.csv')):
        rows = list(csv.DictReader(path.open()))
        db.executemany('INSERT INTO movement VALUES (?,?,?,?)', [tuple(r.values()) for r in rows])
    rows = list(csv.DictReader((folder / 'reservations.csv').open()))
    db.executemany('INSERT INTO reservation VALUES (?,?,?,?,?)', [tuple(r.values()) for r in rows])
    sql = '''WITH m AS (SELECT warehouse,sku,SUM(delta) net FROM
               (SELECT DISTINCT id,warehouse,sku,delta FROM movement) GROUP BY warehouse,sku),
             r AS (SELECT warehouse,sku,SUM(qty) reserved FROM reservation WHERE status='active'
                   GROUP BY warehouse,sku),
             a AS (SELECT o.*,m.net,COALESCE(r.reserved,0) reserved,c.pack,c.threshold+? target,
                   o.opening+m.net-COALESCE(r.reserved,0) available
                   FROM opening o JOIN catalog c USING(sku) JOIN m USING(warehouse,sku)
                   LEFT JOIN r USING(warehouse,sku)),
             b AS (SELECT *,MAX(0,target-available) deficit FROM a)
             SELECT *,((deficit+pack-1)/pack)*pack reorder FROM b ORDER BY warehouse,sku'''
    items = [dict(r) for r in db.execute(sql, (offset,))]
    warehouses = [dict(warehouse=w, reorder=sum(r['reorder'] for r in items if r['warehouse']==w),
                       deficit=sum(r['deficit'] for r in items if r['warehouse']==w),
                       available=sum(r['available'] for r in items if r['warehouse']==w))
                  for w in ('W1','W2','W3','W4')]
    top = sorted(items, key=lambda r:(-r['deficit'],r['warehouse'],r['sku']))[:10]
    return dict(offset=offset,items=items,warehouses=warehouses,top10=top,
                counts=dict(catalog=80,opening=320,movements_raw=3216,movements_unique=3200,
                            duplicate_movements=16,reservations=480,active_reservations=384,
                            cancelled_reservations=96))


def validate(folder, offset):
    expected = oracle(offset); actual = json.loads((folder/'inventory.json').read_text())
    checks = {}
    for key in ('offset','items','warehouses','top10','counts'):
        checks[key] = actual.get(key) == expected[key]
    md = (folder/'report.md').read_text()
    checks['report_tables'] = all(w['warehouse'] in md and str(w['reorder']) in md
                                 for w in expected['warehouses']) and all(r['sku'] in md for r in expected['top10'])
    checks['report_nonempty'] = len(md) > 350
    aliases={'창고':'warehouse','상품':'sku','기초':'opening','순증감':'net','예약':'reserved',
             '목표':'target','가용':'available','부족':'deficit','발주':'reorder','active 예약':'reserved'}
    tables=[]; lines=md.splitlines(); index=0
    while index<len(lines)-1:
        if lines[index].startswith('|') and lines[index+1].startswith('|') and '---' in lines[index+1]:
            headers=[aliases.get(x.strip(),x.strip()) for x in lines[index].strip('|').split('|')]
            rows=[]; index+=2
            while index<len(lines) and lines[index].startswith('|'):
                rows.append(dict(zip(headers,[x.strip() for x in lines[index].strip('|').split('|')])));index+=1
            tables.append(rows)
        else:index+=1
    warehouse_table=next((t for t in tables if t and 'warehouse' in t[0] and 'sku' not in t[0]),[])
    top_table=next((t for t in tables if t and 'sku' in t[0]),[])
    def same(shown,wanted):
        return all(k in wanted and str(wanted[k])==str(v).replace(',','') for k,v in shown.items())
    filtered=[r for r in warehouse_table if r.get('warehouse') in ('W1','W2','W3','W4')]
    checks['report_warehouse_values']=len(filtered)==4 and all(same(a,b) for a,b in zip(filtered,expected['warehouses']))
    checks['report_top10_values']=len(top_table)==10 and all(same(a,b) for a,b in zip(top_table,expected['top10']))
    result = dict(folder=str(folder),offset=offset,checks=checks,passed=all(checks.values()))
    dump(folder/'validation.json',result)
    return result


if __name__ == '__main__':
    if len(sys.argv)==1: generate()
    else: print(json.dumps(validate(Path(sys.argv[1]),int(sys.argv[2])),ensure_ascii=False))
