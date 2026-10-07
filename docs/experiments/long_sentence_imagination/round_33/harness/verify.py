"""산출물을 독립 oracle 과 전건 대조한다. 사용: verify.py <variant> <out_dir> [--oracle 파일]"""
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-07_33회차'


def norm_num(v):
    if isinstance(v, float) and v == int(v):
        return int(v)
    return v


def valid_cycle(path, bom):
    if not path or len(path) < 2 or path[-1] not in path[:-1]:
        return False
    edges = {(e['parent'], e['child']) for e in bom}
    return all((a, b) in edges for a, b in zip(path, path[1:]))


def main():
    variant, out_dir = sys.argv[1], Path(sys.argv[2])
    oracle_file = Path(sys.argv[sys.argv.index('--oracle') + 1]) if '--oracle' in sys.argv else OUT / 'oracle' / f'{variant}.json'
    oracle = json.load(open(oracle_file))
    bom = json.load(open(OUT / 'source' / variant / 'bom.json'))
    result = json.load(open(out_dir / 'result.json'))
    report = (out_dir / 'report.md').read_text()
    checks = []

    def check(name, ok, detail=None):
        checks.append({'check': name, 'ok': bool(ok), 'detail': detail})

    # 1. orders
    o_res = {o['order_id']: o for o in result['orders']}
    o_exp = {o['order_id']: o for o in oracle['orders']}
    check('orders_count', len(o_res) == len(o_exp) == 20, (len(o_res), len(o_exp)))
    bad = []
    for oid, exp in o_exp.items():
        got = o_res.get(oid) or {}
        if any(got.get(k) != exp[k] for k in ('product', 'qty', 'status', 'leaf_rows')):
            bad.append((oid, {k: (got.get(k), exp[k]) for k in ('product', 'qty', 'status', 'leaf_rows')}))
        if exp['status'] == '순환' and not valid_cycle(got.get('cycle_path'), bom):
            bad.append((oid, 'cycle_path invalid', got.get('cycle_path')))
        if exp['status'] == '산출' and got.get('cycle_path') is not None:
            bad.append((oid, 'cycle_path should be null'))
    check('orders_fields', not bad, bad[:5])
    # 2. requirements
    r_res = {r['part']: r for r in result['requirements']}
    r_exp = {r['part']: r for r in oracle['requirements']}
    check('requirements_part_set', set(r_res) == set(r_exp), {'missing': sorted(set(r_exp) - set(r_res))[:5], 'extra': sorted(set(r_res) - set(r_exp))[:5]})
    bad = []
    for part, exp in r_exp.items():
        got = r_res.get(part) or {}
        for k in ('name', 'type', 'gross', 'on_hand', 'shortage', 'status'):
            if norm_num(got.get(k)) != norm_num(exp[k]):
                bad.append((part, k, got.get(k), exp[k]))
    check('requirements_fields', not bad, bad[:8])
    check('requirements_sorted', [r['part'] for r in result['requirements']] == sorted(r_res), None)
    # 3. honesty statuses
    unk = [r for r in oracle['requirements'] if r['status'] == '재고 미상']
    check('unknown_stock_null', all(r_res[r['part']]['shortage'] is None and r_res[r['part']]['on_hand'] is None for r in unk), len(unk))
    # 4. depth / events
    dbp = result['depth_by_product']
    if isinstance(dbp, list):
        dbp = {r['product']: r['depth'] for r in dbp}
    check('depth_by_product', dbp == oracle['depth_by_product'], {'got': dbp, 'exp': oracle['depth_by_product']} if dbp != oracle['depth_by_product'] else None)
    check('max_depth', result['max_depth'] == oracle['max_depth'], (result['max_depth'], oracle['max_depth']))
    check('events', result['events'] == oracle['events'], (result['events'], oracle['events']))
    # 5. report sections
    for sec in ('주문별 상태', '부족 상위', '재고 미상', '순환'):
        check(f'report_section:{sec}', sec in report)
    short = sorted((r for r in oracle['requirements'] if r['status'] == '부족'), key=lambda r: -r['shortage'])[:10]
    check('report_top_shortages', all(r['part'] in report for r in short), [r['part'] for r in short])
    check('report_orders_listed', all(o in report for o in o_exp))
    cyc = [o for o in oracle['orders'] if o['status'] == '순환']
    check('report_cycles_listed', all(o['order_id'] in report for o in cyc), len(cyc))
    ok = all(c['ok'] for c in checks)
    print(json.dumps({'variant': variant, 'out': str(out_dir), 'all_ok': ok, 'checks': checks}, ensure_ascii=False, indent=1))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
