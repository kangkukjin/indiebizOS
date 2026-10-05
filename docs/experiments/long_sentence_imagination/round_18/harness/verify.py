import json,sys,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
who,kind=sys.argv[1],sys.argv[2]   # trainer|agent , base|variant
exp=json.load(open(ROOT/f'harness/expected_{kind}.json'))
d=ROOT/who/kind; out={'who':who,'kind':kind}
try: act=json.load(open(d/'result.json'))
except Exception as e: print(json.dumps({'error':str(e)})); sys.exit()
for k in exp:
    a=act.get(k); out[k]= (a==exp[k])
    if a!=exp[k]:
        if isinstance(a,list) and isinstance(exp[k],list):
            diff=[(x,y) for x,y in zip(a,exp[k]) if x!=y][:3]; out[k+'_diff']={'len':[len(a),len(exp[k])],'first':diff}
        else: out[k+'_diff']=[a,exp[k]]
out['extra_keys']=sorted(set(act)-set(exp))
md=(d/'report.md').read_text() if (d/'report.md').exists() else ''
out['md_chars']=len(md)
out['md_summary_values']=all(str(v) in md for v in exp['summary'].values())
out['md_top10']=all(r['project'] in md and str(r['duration']) in md for r in exp['top10'])
out['md_owners']=all(o['owner'] in md for o in exp['owners'])
out['md_excluded']=all(e['project'] in md for e in exp['excluded'])
if kind=='variant':
    ed=json.load(open(ROOT/'harness/expected_delta.json'))
    try:
        ad=json.load(open(d/'delta.json'))
        for k in ed:
            out['delta_'+k]=(ad.get(k)==ed[k])
            if ad.get(k)!=ed[k]: out['delta_'+k+'_diff']=[str(ad.get(k))[:300],str(ed[k])[:300]]
    except Exception as e: out['delta_error']=str(e)
json.dump(out,open(ROOT/f'harness/{who}_{kind}_validation.json','w'),ensure_ascii=False,indent=1)
print(json.dumps(out,ensure_ascii=False))
