"""Independent Decimal oracle, not used by either task executor."""
import argparse
import json
from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-12_58회차'


def expected(directory, limit, budget):
    def read(name):
        return json.loads((directory / (name + '.json')).read_text(), parse_float=Decimal)
    needs, quotes, vendors = map(read, ['requirements', 'quotes', 'vendors'])
    selected, evaluated = [], []
    for n in needs:
        candidates = []
        for q in quotes:
            if q['sku'] != n['sku']:
                continue
            row = dict(n, **q)
            reason = ('가격 미상' if q.get('price') is None else '포장 오류' if q['pack'] <= 0
                      else '납기 초과' if q['days'] > limit else '')
            if not reason:
                packs = (n['needed'] + q['pack'] - 1) // q['pack']
                quantity = packs * q['pack']
                if quantity > q['stock']:
                    reason = '재고 부족'
                else:
                    goods = int((packs * Decimal(q['price']) * (Decimal(1) if q['tax_included'] else Decimal('1.1'))).quantize(Decimal(1), rounding=ROUND_HALF_EVEN))
                    row.update(packs=packs, quantity=quantity, surplus=quantity-n['needed'], goods=goods)
            row.update(eligible=not reason, reason=reason)
            evaluated.append(row)
            if not reason:
                candidates.append(row)
        if candidates:
            selected.append(dict(min(candidates, key=lambda r:(r['goods'],r['days'],r['quote_id'])),status='선택'))
        else:
            selected.append(dict(n,status='후보 없음'))
    orders = []
    for v in vendors:
        rows = [r for r in selected if r.get('vendor') == v['vendor']]
        if not rows:
            continue
        goods = sum(r['goods'] for r in rows)
        shipping = 0 if goods >= v['threshold'] else v['shipping']
        orders.append(dict(v, goods=goods, lines=len(rows), shipping=shipping,
                           total=None if shipping is None else goods+shipping))
    unknown = [r['vendor'] for r in orders if r['shipping'] is None]
    known = sum(r['goods']+(r['shipping'] or 0) for r in orders)
    total = None if unknown else known
    return dict(selected=selected,evaluated=evaluated,orders=orders,known=known,total=total,
                unknown_vendors=unknown,budget=budget,within_budget=None if total is None else total<=budget)


if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('result'); p.add_argument('--input',default=str(OUT/'input')); p.add_argument('--limit',type=int,default=7); p.add_argument('--budget',type=int,default=1500000); a=p.parse_args()
    want=expected(Path(a.input),a.limit,a.budget)
    actual=json.loads(Path(a.result).read_text(),parse_float=Decimal)
    errors=[]
    for key in want:
        left,right=actual.get(key),want[key]
        if key in ('selected','evaluated','orders'):
            index={'selected':'sku','evaluated':'quote_id','orders':'vendor'}[key]
            left=sorted(left or [],key=lambda r:r[index]); right=sorted(right,key=lambda r:r[index])
        if left != right:
            errors.append(key)
    print(json.dumps(dict(match=not errors,differences=errors,expected_summary={k:v for k,v in want.items() if k not in ('selected','evaluated','orders')},rows={k:len(want[k]) for k in ('selected','evaluated','orders')}),ensure_ascii=False))
    raise SystemExit(bool(errors))
