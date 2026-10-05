"""Synthetic inputs and independent imperative FIFO oracle; no live data."""
import csv
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-05_19회차'


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2))


def oracle(skus, lots, orders, cancellations):
    cancel = set(cancellations)
    known = {r['sku'] for r in skus}
    unique = {r['order']: r for r in orders}
    balances = {r['lot']: r['qty'] for r in lots}
    allocations, results = [], []
    for row in sorted(unique.values(), key=lambda r: (r['seq'], r['order'])):
        raw = row['qty']
        try:
            qty = float(raw)
            valid = qty > 0 and qty.is_integer()
        except (ValueError, TypeError):
            qty, valid = None, False
        qty = int(qty) if valid else None
        status = ('cancelled' if row['order'] in cancel else
                  'invalid_qty' if not valid else
                  'unknown_sku' if row['sku'] not in known else None)
        allocated = cost = 0
        if status is None:
            for lot in sorted((r for r in lots if r['sku'] == row['sku']),
                              key=lambda r: (r['received'], r['lot'])):
                used = min(qty - allocated, balances[lot['lot']])
                if used:
                    allocations.append(dict(order=row['order'], sku=row['sku'],
                                            lot=lot['lot'], qty=used, cost=used*lot['unit_cost']))
                    allocated += used
                    cost += used * lot['unit_cost']
                    balances[lot['lot']] -= used
                if allocated == qty:
                    break
            status = 'fulfilled' if allocated == qty else 'partial' if allocated else 'shortage'
        results.append(dict(order=row['order'], sku=row['sku'], qty=qty,
                            status=status, allocated=allocated, cost=cost,
                            shortage=(qty-allocated if status in ['fulfilled','partial','shortage'] else 0)))
    stocks = [dict(sku=r['sku'], lot=r['lot'], remaining=balances[r['lot']]) for r in lots]
    summary = dict(raw_orders=len(orders), unique_orders=len(unique),
                   duplicate_rows=len(orders)-len(unique), lots=len(lots),
                   requested=sum(r['qty'] for r in results if r['status'] in ['fulfilled','partial','shortage']),
                   allocated=sum(r['allocated'] for r in results),
                   shortage=sum(r['shortage'] for r in results),
                   remaining=sum(balances.values()), cost=sum(r['cost'] for r in results))
    for status in ['fulfilled','partial','shortage','cancelled','invalid_qty','unknown_sku']:
        summary[status+'_orders'] = sum(r['status'] == status for r in results)
    return dict(summary=summary, orders=sorted(results,key=lambda r:r['order']),
                allocations=sorted(allocations,key=lambda r:(r['order'],r['lot'])),
                lots=sorted(stocks,key=lambda r:r['lot']),
                unknown_cancellations=sorted(cancel-set(unique)))


def main():
    for name in ['inputs','harness','drafts','runs','trainer/base','trainer/variant','agent/base','agent/variant']:
        (OUT/name).mkdir(parents=True,exist_ok=True)
    rng=random.Random(1905)
    skus=[{'sku':f'S{i:03d}'} for i in range(60)]
    lots=[dict(sku=f'S{s:03d}',lot=f'L{s:03d}-{j}',received=f'2026-09-{1+j//2:02d}',
               qty=15+(s*7+j*11)%45,unit_cost=100+s*3+j*17)
          for s in range(59) for j in range(8)]
    orders=[dict(order=f'O{s:03d}-{j:02d}',sku=f'S{s:03d}',seq=j//2,
                 qty=str(3+(s*13+j*7)%19)) for s in range(60) for j in range(30)]
    for n,raw in enumerate(['','미정','0','-2','1.5']): orders[n]['qty']=raw
    for n in range(4): orders[30+n]['sku']='MISSING'
    orders += [dict(r) for r in orders[100:110]]
    cancellations=[r['order'] for r in orders[:1800:17]]+['O000-00','NO-SUCH-1','NO-SUCH-2']
    cancellations += cancellations[:3]
    base=oracle(skus,lots,orders,[])
    variant=oracle(skus,lots,orders,cancellations)
    before={r['order']:r for r in base['orders']}
    delta=[dict(order=r['order'],allocated_before=before[r['order']]['allocated'],
                allocated_after=r['allocated'],cost_before=before[r['order']]['cost'],cost_after=r['cost'])
           for r in variant['orders'] if r!=before[r['order']]]
    rng.shuffle(lots); rng.shuffle(orders)
    save(OUT/'inputs/skus.json',skus)
    save(OUT/'inputs/lots.json',lots)
    save(OUT/'inputs/cancellations.json',cancellations)
    with (OUT/'inputs/orders.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['order','sku','seq','qty']); w.writeheader(); w.writerows(orders)
    save(OUT/'harness/expected_base.json',base)
    save(OUT/'harness/expected_variant.json',variant)
    save(OUT/'harness/expected_delta.json',delta)
    print(json.dumps({'base':base['summary'],'variant':variant['summary'],'delta_rows':len(delta)},ensure_ascii=False))


if __name__ == '__main__':
    main()
