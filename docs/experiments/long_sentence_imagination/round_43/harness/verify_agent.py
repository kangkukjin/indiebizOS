"""독립 AI 산출물 검수 — 구조가 다르므로 oracle 과 느슨하게 대조(축 세분은 거친 축으로 합침). 사용: verify_agent.py <agent_out> <agent_input> <oracle> <qa.json>"""
import csv, json, sys
from pathlib import Path
from PIL import Image
COARSE = {'P1': 'time', 'P3': 'time', 'P2': 'confidence', 'P4': 'confidence', 'P5': 'cost_waste', 'P6': 'cost_waste'}

def main(out, inp, oracle, qa):
    exp = json.loads((oracle / 'expected.json').read_text())
    labels = {r['id']: r['label'] for r in csv.DictReader(open(oracle / 'labels.csv', newline=''))}
    reviews = {r['id']: r['text'] for r in csv.DictReader(open(inp / 'voice' / 'reviews.csv', newline=''))}
    checks, detail = {}, {}
    judged = list(csv.DictReader(open(out / 'analysis' / 'review_judgments.csv', newline='')))
    def coarse(r):
        if r['verdict'] == '제외': return 'noise'
        return COARSE.get(r['axis'], r['axis'])
    agree = sum(1 for r in judged if coarse(r) == labels.get(r['id']))
    detail['agreement_coarse'] = {'agree': agree, 'total': len(judged), 'rate': round(agree / len(judged), 4),
                                  'disagreements': [{'id': r['id'], 'oracle': labels.get(r['id']), 'ai': coarse(r), 'axis': r['axis']} for r in judged if coarse(r) != labels.get(r['id'])]}
    checks['rows_123'] = len(judged) == 123
    checks['text_preserved'] = all(reviews.get(r['id']) == r['text'] for r in judged)
    axes = json.loads((out / 'analysis' / 'voice_axes.json').read_text())['axes']
    detail['axes'] = [(a['axis'], a['count']) for a in axes]
    checks['quotes_exact'] = all(reviews.get(q['id']) == q['text'] for a in axes for q in a['quotes'])
    checks['excluded_12'] = json.loads((out / 'analysis' / 'voice_axes.json').read_text())['excluded'] == 12
    brief = json.loads((out / 'brief.json').read_text())
    bt = json.dumps(brief, ensure_ascii=False)
    import re, glob
    # RTB: '지역 신문 소개' 가 제외 표기 없이 근거로 실렸는지만 본다
    checks['rtb_no_unverified'] = len(brief.get('rtb', [])) == 2 and all(r.get('verified') is True for r in brief.get('rtb', []))
    # 금지어: 소재 문안(copy.json)과 카피 후보에서만 본다(톤 절의 금지어 목록은 제외)
    copies = ' '.join(Path(f).read_text() for f in glob.glob(str(out / 'assets' / '*' / 'copy.json')))
    checks['banned_absent_in_assets'] = not any(w in copies for w in exp['banned_words'])
    ledger = json.loads((out / 'campaign_ledger.json').read_text())
    lrows = ledger if isinstance(ledger, list) else (ledger.get('items') or ledger.get('assets') or ledger.get('rows') or [v for v in ledger.values() if isinstance(v, list)][0])
    detail['ledger_ids'] = [r.get('asset_id') for r in lrows]
    checks['ledger_3_unique'] = len(lrows) == 3 and len({r.get('asset_id') for r in lrows}) == 3
    pngs = {}
    for a in ('A1', 'A2', 'A3'):
        d = {}
        for f in ('image.png', 'card.png'):
            p = out / 'assets' / a / f
            try:
                with Image.open(p) as im: d[f] = im.size
            except Exception as e: d[f] = str(e)
        pngs[a] = d
    detail['pngs'] = pngs
    checks['png_6_valid'] = all(isinstance(v.get('image.png'), tuple) and isinstance(v.get('card.png'), tuple) for v in pngs.values())
    checks['image_square'] = all(v['image.png'][0] == v['image.png'][1] for v in pngs.values() if isinstance(v.get('image.png'), tuple))
    bundle = sorted(p.name for p in (out / 'bundle').iterdir())
    detail['bundle'] = bundle
    checks['bundle_3'] = len(bundle) == 3
    se = json.loads((out / 'analysis' / 'search_terms_evidence.json').read_text())
    detail['search_rows'] = se.get('rows')
    checks['search_total_found'] = all(isinstance(r.get('blog'), int) and r['blog'] > 10 for r in se.get('rows', []))
    result = {'checks': checks, 'all_pass': all(checks.values()), 'detail': detail}
    qa.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({'all_pass': result['all_pass'], 'checks': checks, 'agreement_coarse': detail['agreement_coarse']['rate'], 'axes': detail['axes']}, ensure_ascii=False))

if __name__ == '__main__':
    main(*(Path(a).resolve() for a in sys.argv[1:5]))
