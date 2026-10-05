import json,sys,os,re
from pathlib import Path
from collections import Counter
args=json.load(sys.stdin); expected=args['expected']; actual=args['actual']; md=args['markdown']
def normalized(x,ordered=False):
    if isinstance(x,list):
        vals=[normalized(v) for v in x]
        return vals if ordered else sorted(vals,key=lambda v:json.dumps(v,sort_keys=True))
    if isinstance(x,dict): return {k:normalized(v) for k,v in sorted(x.items())}
    return x
checks=[]
for key,value in expected.items():
    observed=actual.get(key)
    equal=observed==value if key=='top10' else normalized(observed)==normalized(value)
    checks.append(dict(section=key,equal=equal,expected_rows=len(value) if isinstance(value,list) else None,actual_rows=len(observed) if isinstance(observed,list) else None))
nums=md.replace(',','')
summary_present={k:bool(re.search(r'(?<!\d)'+str(v)+r'(?!\d)',nums)) for k,v in expected['summary'].items()}
reasons=Counter(x['reason'] for x in expected['excluded'])
reason_present={k:k in md and bool(re.search(r'(?<!\d)'+str(v)+r'(?!\d)',nums)) for k,v in reasons.items()}
top_present=[]
for r in expected['top10']:
    lines=[line for line in md.splitlines() if r['room'] in line]
    top_present.append(dict(room=r['room'],present=any(r['building'] in line and str(r['usable_count']) in line and str(r['impacted_unique']) in line for line in lines)))
sources=all(name in md for name in ['bookings_a.csv','bookings_b.json','rooms.json','maintenance.csv'])
result=dict(label=args['label'],all_json_equal=all(x['equal'] for x in checks),checks=checks,summary_numbers_present=summary_present,reason_numbers_present=reason_present,top_rows_present=top_present,sources_present=sources,markdown_manual_review_required=True)
Path(os.environ['INDIEBIZ_SCRIPT_RESULT']).write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
