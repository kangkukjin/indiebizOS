"""Synthetic fixtures and independent oracle; never supplied to the system AI."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-06_25회차'


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2))


def generate():
    source = OUT / 'source'
    source.mkdir(parents=True, exist_ok=True)
    orders = []
    for i in range(1200):
        lines = []
        for j in range(3):
            k = 3 * i + j
            row = dict(line_no=str(j + 1), sku=f'S{k % 80:02}', qty=1 + k % 5,
                       note=['첫 줄\r\n둘째 줄', '탭\t보존', '쉼표,따옴표"', ''][k % 4])
            if k % 7 == 0:
                row['order_id'] = f'VENDOR-{k}'
            if k % 97 == 0:
                row['sku'] = 'UNKNOWN'
            lines.append(row)
        orders.append(dict(order_id=f'O{i:04}', region=f'R{i % 6}', lines=lines))
    for shard in range(3):
        values = orders[400 * shard:400 * (shard + 1)]
        # Exact resubmission duplicates; first row wins.
        dump(source / f'orders_{shard}.json', values + values[:10])
    with (source / 'prices.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['sku', 'unit_price', 'note'])
        writer.writeheader()
        for i in range(80):
            writer.writerow(dict(sku=f'S{i:02}', unit_price=1000 + 100 * i,
                                 note=f'단가\r\n메모{i}'))
    returns = []
    for i in range(1200):
        if i % 4 == 0:
            returns.append(dict(order_id=f'O{i:04}', line_no='2', returned_qty=1))
            returns.append(dict(order_id=f'O{i:04}', line_no='2', returned_qty=1))
    with (source / 'returns.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['order_id', 'line_no', 'returned_qty'])
        writer.writeheader()
        writer.writerows(returns)
    for name in ['trainer', 'ai', 'evidence', 'runs']:
        (OUT / name).mkdir(exist_ok=True)
    return source


def oracle(missing=None, threshold=30000):
    source = OUT / 'source'
    prices = {}
    with (source / 'prices.csv').open(newline='') as f:
        for row in csv.DictReader(f):
            prices[row['sku']] = int(row['unit_price'])
    returns = {}
    with (source / 'returns.csv').open(newline='') as f:
        for row in csv.DictReader(f):
            key = (row['order_id'], row['line_no'])
            returns[key] = returns.get(key, 0) + int(row['returned_qty'])
    seen, rows, regions = set(), [], {}
    for shard in range(3):
        if shard == missing:
            continue
        for order in json.loads((source / f'orders_{shard}.json').read_text()):
            for line in order['lines']:
                key = (order['order_id'], line['line_no'])
                if key in seen:
                    continue
                seen.add(key)
                returned = returns.get(key, 0)
                price = prices.get(line['sku'])
                status = 'excess_return' if returned > line['qty'] else 'unknown_price' if price is None else 'ok'
                net = line['qty'] - returned
                amount = net * price if status == 'ok' else None
                eligible = amount is not None and amount >= threshold
                row = dict(order_id=key[0], line_no=key[1], region=order['region'],
                           sku=line['sku'], qty=line['qty'], returned_qty=returned,
                           unit_price=price, net_qty=net, amount=amount, status=status,
                           eligible=eligible, note=line['note'], vendor_order_id=line.get('order_id'))
                rows.append(row)
                summary = regions.setdefault(order['region'], dict(region=order['region'], lines=0,
                    amount=0, anomalies=0, eligible=0))
                summary['lines'] += 1
                summary['amount'] += amount or 0
                summary['anomalies'] += int(status != 'ok')
                summary['eligible'] += int(eligible)
    return dict(rows=rows, summary=list(regions.values()), total_amount=sum(r['amount'] or 0 for r in rows),
                count=len(rows), threshold=threshold)


if __name__ == '__main__':
    generate()
    for name, missing, threshold in [('main', None, 30000), ('policy', None, 50000), ('missing', 1, 30000)]:
        result = oracle(missing, threshold)
        dump(OUT / 'evidence' / f'expected_{name}.json', result)
        print(name, result['count'], result['total_amount'], sum(r['eligible'] for r in result['rows']),
              sum(r['status'] != 'ok' for r in result['rows']))
