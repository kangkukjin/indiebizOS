"""33회차 합성 자료와 독립 oracle. IBL 과제 계산은 하지 않는다(oracle 은 대조용, AI 입력 사본에서 제외)."""
import json
import random
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-07_33회차'
DOC = Path(__file__).resolve().parents[1]


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2))


def build_base():
    rng = random.Random(33)
    products = [f'P{i:02d}' for i in range(1, 11)]
    tiers = [[f'S{i:02d}' for i in range(1, 21)], [f'S{i:02d}' for i in range(21, 41)],
             [f'S{i:02d}' for i in range(41, 56)], [f'S{i:02d}' for i in range(56, 61)]]
    raws = [f'R{i:03d}' for i in range(1, 201)]
    parts = [{'part': p, 'name': f'완제품 {p}', 'type': '제품', 'unit': 'ea'} for p in products]
    for tier in tiers:
        parts += [{'part': s, 'name': f'모듈 {s}', 'type': '반제품', 'unit': 'ea'} for s in tier]
    parts += [{'part': r, 'name': f'자재 {r}', 'type': '구매품', 'unit': 'kg' if int(r[1:]) % 5 == 0 else 'ea'} for r in raws]
    qtys = [1, 1, 2, 2, 3, 4, '0.5', '0.25', '1.5']
    bom = []

    def add(parent, children):
        for c in children:
            q = rng.choice(qtys)
            bom.append({'parent': parent, 'child': c, 'qty_per': float(q) if isinstance(q, str) else q})
    for p in products:
        add(p, rng.sample(tiers[0], rng.randint(2, 3)) + rng.sample(raws, rng.randint(1, 2)))
    for ti, tier in enumerate(tiers):
        for s in tier:
            deeper = tiers[ti + 1] if ti + 1 < len(tiers) else []
            kids = (rng.sample(deeper, rng.randint(1, 2)) if deeper else []) + rng.sample(raws, rng.randint(1, 2))
            add(s, kids)
    rng.shuffle(bom)
    orders = [{'order_id': f'O{i:03d}', 'product': rng.choice(products), 'qty': rng.randint(5, 120)} for i in range(1, 21)]
    stocked = rng.sample(raws, 180)
    stock = [{'part': r, 'on_hand': rng.randint(0, 3000)} for r in sorted(stocked)]
    stock += [{'part': s, 'on_hand': 7} for s in ['S03', 'S27', 'S44']]  # 반제품 재고(집계 대상 아님)
    rng.shuffle(stock)
    return parts, bom, orders, stock


def build_cycle(parts, bom, orders, stock):
    """기본 bom 에 (1) 조상으로 되돌아가는 순환 (2) parts 에 없는 부품 (3) 구성 없는 반제품을 주입한다."""
    kids = defaultdict(list)
    for e in bom:
        kids[e['parent']].append(e['child'])
    ordered_products = [o['product'] for o in orders]
    # (1) 주문된 첫 제품의 1층→2층→3층 경로 끝에서 1층으로 되돌리는 간선
    p0 = ordered_products[0]
    sa = next(c for c in kids[p0] if c.startswith('S'))
    sb = next(c for c in kids[sa] if c.startswith('S'))
    sc = next(c for c in kids[sb] if c.startswith('S'))
    bom = list(bom) + [{'parent': sc, 'child': sa, 'qty_per': 1}]
    # (2) 순환과 무관한 다른 제품의 1층 모듈 아래에 정의 없는 구매품·정의 없는 반제품
    others = [p for p in ordered_products if p != p0 and sa not in reach(kids, p)]
    s_other = next(c for c in kids[others[0]] if c.startswith('S'))
    bom += [{'parent': s_other, 'child': 'R999', 'qty_per': 2}, {'parent': s_other, 'child': 'S99', 'qty_per': 1}]
    # (3) 같은 제품 아래 깊은 반제품 하나의 구성을 전부 제거 → 구성 없음
    deep = sorted(x for x in reach(kids, others[0]) if x.startswith('S') and x not in reach(kids, sa))[-1]
    bom = [e for e in bom if e['parent'] != deep]
    return parts, bom, orders, stock


def reach(kids, root):
    seen, stack = set(), [root]
    while stack:
        x = stack.pop()
        for c in kids.get(x, []):
            if c not in seen:
                seen.add(c); stack.append(c)
    return seen


def num(d):
    return int(d) if d == d.to_integral_value() else float(d)


def oracle(parts, bom, orders, stock):
    kids = defaultdict(list)
    for e in bom:
        kids[e['parent']].append((e['child'], Decimal(str(e['qty_per']))))
    ptype = {p['part']: p['type'] for p in parts}
    pname = {p['part']: p['name'] for p in parts}
    onhand = {s['part']: s['on_hand'] for s in stock}
    counts = defaultdict(int)
    for s in stock:
        counts[s['part']] += 1
    duplicated = {part for part, n in counts.items() if n > 1}   # 같은 부품의 재고 행 2개 이상 → 재고 중복(합치거나 고르지 않는다)
    gross = defaultdict(Decimal)
    order_rows, depth_by_product = [], {}
    max_depth = 0
    for o in orders:
        leaves, cyc = [], []
        stack = [(o['product'], Decimal(o['qty']), 0, [o['product']])]
        while stack:
            part, qty, level, path = stack.pop()
            if part not in kids:
                leaves.append((part, qty, level))
                continue
            for child, qp in kids[part]:
                if child in path:
                    cyc.append(path + [child])
                else:
                    stack.append((child, qty * qp, level + 1, path + [child]))
        if cyc:
            order_rows.append({'order_id': o['order_id'], 'product': o['product'], 'qty': o['qty'],
                               'status': '순환', 'leaf_rows': len(leaves), 'cycle_path': sorted(cyc)[0]})
            continue
        d = max(l for _, _, l in leaves)
        depth_by_product[o['product']] = max(depth_by_product.get(o['product'], 0), d)
        max_depth = max(max_depth, d)
        for part, qty, _ in leaves:
            gross[part] += qty
        order_rows.append({'order_id': o['order_id'], 'product': o['product'], 'qty': o['qty'],
                           'status': '산출', 'leaf_rows': len(leaves), 'cycle_path': None})
    req = []
    for part in sorted(gross):
        g = gross[part]
        if part not in ptype:
            status, sh = '정의 없음', None
        elif ptype[part] != '구매품':
            status, sh = '구성 없음', None
        elif part in duplicated:
            status, sh = '재고 중복', None
        elif part not in onhand:
            status, sh = '재고 미상', None
        else:
            sh = max(g - Decimal(onhand[part]), Decimal(0))
            status = '부족' if g > onhand[part] else '충분'
        req.append({'part': part, 'name': pname.get(part), 'type': ptype.get(part),
                    'gross': num(g), 'on_hand': None if part in duplicated else onhand.get(part),
                    'shortage': num(sh) if sh is not None else None,
                    'status': status})
    return {'requirements': req, 'orders': order_rows, 'depth_by_product': depth_by_product,
            'max_depth': max_depth, 'events': len(bom)}


def main():
    base = build_base()
    cyc = build_cycle(*base)
    for name, data in (('base', base), ('cycle', cyc)):
        parts, bom, orders, stock = data
        src = OUT / 'source' / name
        dump(src / 'parts.json', parts)
        dump(src / 'bom.json', bom)
        dump(src / 'orders.json', orders)
        dump(src / 'stock.json', stock)
        dump(OUT / 'oracle' / f'{name}.json', oracle(*data))
    print('generated', OUT)


if __name__ == '__main__':
    main()
