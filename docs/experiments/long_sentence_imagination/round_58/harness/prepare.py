"""Synthetic input only; independent oracle is kept outside the AI input folder."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-12_58회차'
for folder in ('input', 'runs', 'trainer', 'ai'):
    (OUT/folder).mkdir(parents=True, exist_ok=True)
needs = [{'sku': f'S{i:04}', 'needed': 1 + i % 37} for i in range(240)]
quotes = []
for i, need in enumerate(needs):
    for j in range(5):
        quotes.append(dict(sku=need['sku'], quote_id=f'Q{i:04}-{j}', vendor=f'V{j}',
                           pack=0 if i % 41 == 0 else j + 1,
                           price=None if i % 43 == 0 else 99.5 + (i % 17)*13 + j*11,
                           stock=0 if j == 0 and i % 7 == 0 else 100,
                           days=2+j*2, tax_included=j % 2 == 0))
vendors = [dict(vendor=f'V{j}', threshold=50000, shipping=None if j == 2 else 3000+j*500) for j in range(5)]
for name, rows in [('requirements',needs),('quotes',quotes),('vendors',vendors)]:
    (OUT/'input'/f'{name}.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
task=(ROOT/'docs/experiments/long_sentence_imagination/round_58/task.md').read_text().split('## 자연어 요구\n')[1].split('\n변형:')[0]
msg=task+f'\n자료: {OUT}/input. 저장: {OUT}/ai/main. 다른 실행자의 trainer/harness/drafts 또는 기대값을 열지 마.'
(OUT/'runs/ai_request.json').write_text(json.dumps(dict(message=msg,origin='training',background=True),ensure_ascii=False))

# 정답은 넣지 않고 원천만 만든다. 역순·부재·동률 경계의 재현 자료.
edge_needs = [r for r in needs if r['sku'] in ('S0001','S0002','S0041')][::-1]
edge_quotes = [r for r in quotes if r['sku'] in ('S0001','S0002','S0041')][::-1]
missing_quotes = [dict(r) for r in edge_quotes]
for row in missing_quotes:
    if row['sku'] == 'S0001' and row['vendor'] == 'V2':
        row.pop('price')
new_needs = [{'sku':'TIE','needed':5},{'sku':'NONE','needed':2}]
new_quotes = [
    dict(sku='TIE',quote_id='Q-B',vendor='V',pack=3,price=110,stock=6,days=3,tax_included=True),
    dict(sku='TIE',quote_id='Q-A',vendor='V',pack=3,price=100,stock=6,days=3,tax_included=False),
    dict(sku='TIE',quote_id='Q-C',vendor='V',pack=3,price=1,stock=5,days=3,tax_included=True),
    dict(sku='NONE',quote_id='Q-D',vendor='V',pack=1,stock=100,days=1,tax_included=True),
]
variants = {
    'edge': (edge_needs, edge_quotes, vendors),
    'missing': (edge_needs, missing_quotes, vendors),
    'empty': ([], [], []),
    'new': (new_needs, new_quotes, [dict(vendor='V',threshold=220,shipping=None)]),
}
for label, tables in variants.items():
    folder = OUT/f'input_{label}'
    folder.mkdir(exist_ok=True)
    for name, rows in zip(('requirements','quotes','vendors'),tables):
        (folder/f'{name}.json').write_text(json.dumps(rows,ensure_ascii=False))
for label, source, limit, budget in [('main','input',7,1500000),('variant','input',3,1000000)]+[
        (name, f'input_{name}', 7, 1500000) for name in variants]:
    request = {
        'code': (ROOT/'docs/experiments/long_sentence_imagination/round_58/drafts/main_v3.ibl').read_text(),
        'origin': 'training', 'project_id': '수동모드',
        'inputs': {'input': str(OUT/source), 'out': str(OUT/f'trainer/replay_{label}'),
                   'limit': limit, 'budget': budget},
        'budget': {'steps':200000,'rows':10000},
    }
    (OUT/f'runs/replay_{label}_request.json').write_text(json.dumps(request,ensure_ascii=False))
