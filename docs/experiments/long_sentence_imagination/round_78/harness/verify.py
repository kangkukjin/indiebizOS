"""Independent numerical oracle; never changes generated artifacts."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-19_78회차'


def expected(variant=False, threshold=50000):
    rows = []
    for i in range(1, 13):
        good = i + 2 + (int(i == 9) + 2 * int(i == 1) + int(i == 12) if variant else 0)
        damaged = i % 3
        source = ['north.txt', 'south.txt', 'west.txt'][(i-1)//4]
        rows.append(dict(id=f'R{i:02}', loaned=10+i, good=good, damaged=damaged,
                         missing=10+i-good-damaged, exposure=(10+i-good)*1000*i,
                         sources=[source] + (['late.txt'] if variant and i in (1, 12) else [])))
    return {'complete':variant, 'rows':rows,
            'totals':{key:sum(row[key] for row in rows) for key in ('loaned','good','damaged','missing','exposure')},
            'recheck':[row['id'] for row in rows if row['exposure'] >= threshold]}


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('label'); parser.add_argument('--variant',action='store_true'); parser.add_argument('--threshold',type=int,default=50000)
    args=parser.parse_args(); folder=OUT/args.label
    actual=json.loads((folder/'report.json').read_text()); wanted=expected(args.variant,args.threshold)
    # AI may choose field names; normalize representation only, never expected values.
    if 'totals_known_rows' in actual:
        aliases={'normal_returned':'good','damaged_returned':'damaged','unreturned':'missing'}
        rows=[{aliases.get(k,k):v for k,v in row.items()} for row in actual['rows']]
        for row in rows:
            row['sources']=list(dict.fromkeys(src.split(':')[0] for src in row['sources']))
        totals={aliases.get(k,k):v for k,v in actual['totals_known_rows'].items() if k!='loaned_all'}
        actual={**actual,'rows':rows,'totals':totals,
                'complete':not actual.get('missing_files') and not actual.get('unparsed_lines') and '잠정' not in actual.get('status',''),
                'missing_sources':[{'source':r['file']} for r in actual.get('missing_files',[])],
                'recheck':[row['id'] for row in rows if row.get('recheck')]}
    checks=[]
    for key in ('complete','totals','recheck'):
        checks.append({'field':key,'ok':actual.get(key)==wanted[key],'actual':actual.get(key),'expected':wanted[key]})
    for row in wanted['rows']:
        got=[item for item in actual.get('rows',[]) if item.get('id')==row['id']]
        checks.append({'field':row['id'],'ok':len(got)==1 and all(got[0].get(k)==v for k,v in row.items()),'actual':got,'expected':row})
    checks.append({'field':'row_count','ok':len(actual.get('rows',[]))==12})
    missing=[r['source'] for r in actual.get('missing_sources',[])]
    checks.append({'field':'missing_sources','ok':missing==([] if args.variant else ['late.txt'])})
    summary=(folder/'summary.md').read_text()
    checks.append({'field':'summary_totals','ok':all(str(v) in summary.replace(',','') for v in wanted['totals'].values())})
    result={'label':args.label,'checks':checks,'passed':sum(c['ok'] for c in checks),'total':len(checks)}
    (OUT/'evidence'/('verify_'+args.label.replace('/','_')+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({'label':args.label,'passed':result['passed'],'total':result['total'],'failures':[c for c in checks if not c['ok']]},ensure_ascii=False))


if __name__ == '__main__':
    main()
