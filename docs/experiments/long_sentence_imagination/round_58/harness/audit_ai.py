"""Compare independently authored AI artifacts with the frozen task oracle."""
import json
from decimal import Decimal

from oracle import OUT, expected


def audit(label, limit, budget):
    actual = json.loads((OUT/f'ai/{label}/result.json').read_text(), parse_float=Decimal)
    want = expected(OUT/'input', limit, budget)
    items = {r['sku']: r for r in actual['items']}
    quotes = {r['quote_id']: r for r in actual['quotes']}
    vendors = {r['vendor']: r for r in actual['vendors']}
    assert len(items) == len(actual['items']) == len(want['selected'])
    assert len(quotes) == len(actual['quotes']) == len(want['evaluated'])
    checked = 2
    mapping = {'quote_id': 'selected_quote_id', 'quantity': 'buy_qty',
               'surplus': 'leftover', 'goods': 'amount', 'packs': 'packs', 'vendor': 'vendor'}
    for r in want['selected']:
        a = items[r['sku']]
        assert a['status'] == r['status']
        if r['status'] == '선택':
            assert all(a[target] == r[key] for key, target in mapping.items()), r['sku']
        checked += 1
    for r in want['evaluated']:
        a = quotes[r['quote_id']]
        assert (a['status'] != '제외') == r['eligible'], r['quote_id']
        if r['eligible']:
            assert a['amount'] == r['goods'] and a['buy_qty'] == r['quantity']
        else:
            assert a['reasons']
        checked += 1
    for r in want['orders']:
        a = vendors[r['vendor']]
        assert (a['subtotal'], a['shipping'], a['vendor_total']) == (r['goods'], r['shipping'], r['total'])
        checked += 1
    assert actual['summary']['known_amount'] == want['known']
    assert actual['summary']['total'] == want['total']
    report = (OUT/f'ai/{label}/report.md').read_text()
    assert all(r['sku'] in report for r in want['selected'])
    assert f"{want['total']:,}" in report
    return {'label': label, 'checked_rows': checked, 'total': want['total'], 'matched': True}


if __name__ == '__main__':
    results = [audit('main', 7, 1500000), audit('variant', 3, 1000000)]
    (OUT/'ai_audit.json').write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(json.dumps(results, ensure_ascii=False))
