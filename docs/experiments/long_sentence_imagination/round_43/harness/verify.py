"""43회차 결정론 검수 — 산출물을 _oracle 과 대조. 사용: verify.py <out_dir> <input_dir> <oracle_dir> <qa.json> [--react]"""
import csv, json, sys
from pathlib import Path

def load_csv(p):
    with open(p, newline='') as f:
        return list(csv.DictReader(f))

def png_ok(p: Path):
    try:
        from PIL import Image
        with Image.open(p) as im:
            return {"exists": True, "size": im.size, "bytes": p.stat().st_size}
    except Exception as e:
        return {"exists": p.exists(), "error": str(e), "bytes": p.stat().st_size if p.exists() else 0}

def verify_base(out: Path, inp: Path, oracle: Path):
    exp = json.loads((oracle / 'expected.json').read_text())
    labels = {r['id']: r['label'] for r in load_csv(oracle / 'labels.csv')}
    reviews = {r['id']: r['text'] for r in load_csv(inp / 'voice' / 'reviews.csv')}
    checks, detail = {}, {}
    cl = json.loads((out / 'research' / 'classified.json').read_text())
    rows = cl['rows']
    agree = sum(1 for r in rows if labels.get(r['id']) == r.get('pain'))
    detail['agreement'] = {"agree": agree, "total": len(rows), "rate": round(agree / len(rows), 4) if rows else None,
                           "disagreements": [{"id": r['id'], "oracle": labels.get(r['id']), "ai": r.get('pain'), "text": reviews.get(r['id'], '')[:60]} for r in rows if labels.get(r['id']) != r.get('pain')]}
    checks['rows_123'] = len(rows) == exp['review_rows']
    checks['text_preserved'] = all(reviews.get(r['id']) == r.get('text') for r in rows)
    brief = json.loads((out / 'brief.json').read_text())
    order = [a['key'] for a in brief['angles']]
    checks['angle_order'] = order == exp['expected_angle_order']
    detail['angle_order'] = order
    detail['axis_counts'] = cl['axis_stats']
    quotes_ok = all(reviews.get(q['id']) == q['text'] for a in brief['angles'] for q in a['quotes'])
    checks['quotes_exact'] = quotes_ok and all(len(a['quotes']) == 2 for a in brief['angles'])
    checks['quotes_match_axis'] = all(labels.get(q['id']) == a['key'] for a in brief['angles'] for q in a['quotes'])
    comp = json.loads((out / 'research' / 'competitors.json').read_text())
    comp_txt = json.dumps(comp, ensure_ascii=False)
    hits = {k: [w for w in ws if w in comp_txt] for k, ws in exp['competitor_expected'].items()}
    detail['competitor_keywords'] = hits
    checks['competitor_price_format'] = all(any(w in comp_txt for w in ws[:2]) for ws in exp['competitor_expected'].values())
    checks['rtb_verified_only'] = all(r.get('verified') for r in brief['rtb']) and len(brief['rtb']) == 2
    ledger = json.loads((out / 'campaign_ledger.json').read_text())
    lrows = ledger['items'] if isinstance(ledger, dict) else ledger
    checks['ledger_3_unique'] = len(lrows) == 3 and len({r['asset_id'] for r in lrows}) == 3
    banned = exp['banned_words']
    recomputed = {r['asset_id']: [w for w in banned if w in ' '.join([r['copy'], r['hook'], r['solution'], r['cta']])] for r in lrows}
    checks['banned_deterministic_match'] = all(recomputed[r['asset_id']] == r['banned_hits'] for r in lrows)
    detail['banned'] = recomputed
    pngs = {}
    for r in lrows:
        pngs[r['asset_id']] = {"image": png_ok(Path(r['image'])), "card": png_ok(Path(r['card']))}
    detail['pngs'] = pngs
    checks['png_6_valid'] = all(v['image'].get('exists') and 'size' in v['image'] and v['card'].get('exists') and 'size' in v['card'] for v in pngs.values())
    checks['image_square'] = all(v['image'].get('size', (0, 1))[0] == v['image'].get('size', (0, 1))[1] for v in pngs.values())
    bundle = sorted(p.name for p in (out / 'bundle').iterdir())
    detail['bundle'] = bundle
    checks['bundle_3'] = bundle == ['checklist.json', 'nip23_draft.md', 'publish_guide.md']
    ck = json.loads((out / 'bundle' / 'checklist.json').read_text())
    checks['not_published'] = ck.get('published') is False and ck.get('sent') is False
    hook_brand = [r['asset_id'] for r in lrows if '수리교실' in r['hook']]
    detail['hook_with_brand'] = hook_brand
    checks['hook_no_brand'] = len(hook_brand) == 0
    se = json.loads((out / 'research' / 'search_terms.json').read_text())
    detail['search_evidence'] = se['evidence']
    return checks, detail

def verify_react(out: Path, inp: Path, oracle: Path):
    exp = json.loads((oracle / 'expected.json').read_text())['reactions']
    perf = json.loads((out / 'performance.json').read_text())
    checks, detail = {}, {}
    got = {a['asset_id']: a for a in perf['by_asset']}
    checks['by_asset_totals'] = all(got[a]['impressions'] == e['impressions'] and got[a]['clicks'] == e['clicks'] and got[a]['inquiries'] == e['inquiries'] for a, e in exp['by_asset'].items())
    checks['ctr_match'] = all((got[a]['ctr'] == e['ctr']) for a, e in exp['by_asset'].items())
    checks['total_inquiries'] = perf['total_inquiries'] == exp['total_inquiries']
    checks['kpi_met'] = perf['kpi_met'] == exp['kpi_met']
    checks['focus_A2'] = perf['focus'] == exp['winning_by_inquiries']
    md = exp['missing_day']
    checks['missing_day_1'] = perf['missing'] == [{"pair": f"{md['asset_id']}|{md['channel']}", "date": md['date']}]
    z = exp['zero_impression_row']
    checks['zero_day_ctr_null'] = len(perf['zero_days']) == 1 and perf['zero_days'][0]['asset_id'] == z['asset_id'] and perf['zero_days'][0]['date'] == z['date'] and perf['zero_days'][0]['ctr'] is None
    checks['unmeasured_2'] = sorted(perf['unmeasured_channels']) == sorted(exp['unmeasured_channels'])
    ledger = json.loads((out / 'campaign_ledger.json').read_text())
    lrows = ledger['items'] if isinstance(ledger, dict) else ledger
    st = {r['asset_id']: r.get('status') for r in lrows}
    detail['ledger_status'] = st
    checks['ledger_statuses'] = st.get('A2') == 'proposal_focus' and st.get('A3') == 'proposal_pause' and st.get('A1') == 'proposal_keep' and len(lrows) == 3
    rep = (out / 'performance.md').read_text()
    checks['report_sections'] = all(h in rep for h in ['## 1. 현황 팩트', '## 2. KPI 대비', '## 3. 소재별 성과', '## 4. 제안'])
    checks['report_mentions_unmeasured'] = '미측정' in rep and '2026-10-15' in rep and '2026-10-12' in rep
    detail['perf'] = {k: perf[k] for k in ('total_inquiries', 'kpi_met', 'focus', 'missing', 'zero_days', 'unmeasured_channels')}
    return checks, detail

if __name__ == '__main__':
    out, inp, oracle, qa = (Path(a).resolve() for a in sys.argv[1:5])
    fn = verify_react if '--react' in sys.argv else verify_base
    checks, detail = fn(out, inp, oracle)
    result = {"checks": checks, "all_pass": all(checks.values()), "detail": detail,
              "scope": "Deterministic artifact QA against synthetic oracle; copy quality and image content are not judged here."}
    qa.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({"all_pass": result['all_pass'], "checks": checks, "agreement": detail.get('agreement', {}).get('rate')}, ensure_ascii=False))
