"""Independent fixture oracle. Reads inputs/outputs; never used by trainees."""
import argparse,collections,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[5]
from prepare import OUT

def load(p):return json.loads(p.read_text())
def canon(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def expected(inp, repaired=False):
    runs=collections.defaultdict(list)
    for r in load(inp/'synthetic/runs.json'):runs[r['run_id']].append(r)
    events=collections.defaultdict(list)
    for p in sorted((inp/'synthetic').glob('events_*.json')):
        for e in load(p):
            if e['kind']=='billable':events[e['event_id']].append(e)
    reqs=load(inp/'synthetic/requirements.json');answer=[]
    for rid,records in runs.items():
        ap=inp/f'synthetic/artifacts/{rid}.json';cp=inp/f'synthetic/checks/{rid}.json'
        a=load(ap) if ap.exists() else None;c=load(cp) if cp.exists() else None
        cond=[]
        for q in (q for q in reqs if q['run_id']==rid):
            k=q['id'];value=a['values'].get(k) if a else None
            current=bool(a and c and a['revision']==c['revision'])
            checked=c['checks'].get(k) if current else None
            state='미충족' if value is False or checked is False else ('충족' if value is True and checked is True else '미검증')
            if repaired:
                state='미검증' if current and value is not None and checked is not None and value != checked else ('미충족' if value is False else '충족' if value is True and checked is True else '미검증')
            cond.append({'id':k,'state':state,'artifact_revision':a['revision'] if a else None,'evidence_revision':c['revision'] if c else None,'source':[str(ap),str(cp)]})
        counts=collections.Counter(c['state'] for c in cond)
        outcome='달성' if cond and counts['충족']==len(cond) else '부분 달성' if counts['충족'] else '미달' if counts['미충족'] else '미검증'
        ie=oe=mi=mo=0;conf=[]
        for eid,es in events.items():
            if es[0]['run_id']!=rid:continue
            if len({canon(e) for e in es})!=1:conf.append(eid);continue
            e=es[0]
            if e['input'] is None:mi+=1
            else:ie+=e['input']
            if e['output'] is None:mo+=1
            else:oe+=e['output']
        answer.append({'run_id':rid,'validation':records[0]['validation'],'execution':'충돌' if len({canon(r) for r in records})>1 else records[0]['execution'],'outcome':outcome,'conditions':cond,'observed_input':ie,'observed_output':oe,'missing_input':mi,'missing_output':mo,'conflict_event_ids':conf,'total_input':None if conf or mi else ie,'total_output':None if conf or mo else oe})
    return answer

def verify(inp,result,report,repaired=False):
    ex=expected(inp,repaired);raw=load(result);actual=raw['runs'] if isinstance(raw,dict) else raw
    errors=[];by={r['run_id']:r for r in actual};checks=0
    if len(actual)!=len(ex) or set(by)!={r['run_id'] for r in ex}:errors.append('run coverage/duplicates')
    for e in ex:
        a=by.get(e['run_id'],{})
        for k,v in e.items():
            checks+=1
            if k=='conditions':
                got={c.get('id'):c for c in a.get(k,[])}
                if len(a.get(k,[]))!=len(v):errors.append(f'{e["run_id"]}.condition coverage')
                for c in v:
                    for f in ('state','artifact_revision','evidence_revision'):
                        if got.get(c['id'],{}).get(f)!=c[f]:errors.append(f'{e["run_id"]}.{c["id"]}.{f}: {got.get(c["id"],{}).get(f)!r} != {c[f]!r}')
                    source=got.get(c['id'],{}).get('source')
                    if not source:errors.append(f'{e["run_id"]}.{c["id"]} missing source')
            elif a.get(k)!=v:errors.append(f'{e["run_id"]}.{k}: {a.get(k)!r} != {v!r}')
    md=report.read_text()
    table_rows={}
    for line in md.splitlines():
        if not line.strip().startswith('|'):continue
        cells=[c.strip().replace('**','').replace('`','') for c in line.strip().strip('|').split('|')]
        if cells and cells[0] in by and len(cells)>=8:table_rows[cells[0]]=cells
    def shown(v):return '미상' if v is None else str(v)
    for e in ex:
        cells=table_rows.get(e['run_id'],[])
        if len(cells)==8:
            observed=[cells[1],cells[2],cells[3],cells[4],cells[5],cells[6]]
            target=[e['validation'],e['execution'],e['outcome'],shown(e['total_input']),shown(e['total_output']),str(e['observed_input'])+'/'+str(e['observed_output'])]
        elif len(cells)==14:
            observed=[cells[2],cells[3],cells[4],cells[8],cells[9],cells[10],cells[12],cells[13]]
            target=[e['validation'],e['execution'],e['outcome'],str(e['observed_input']),str(e['observed_output']),str(e['missing_input'])+'/'+str(e['missing_output']),shown(e['total_input']),shown(e['total_output'])]
        else:
            errors.append(f'{e["run_id"]} report row/schema missing');continue
        checks+=len(target)
        if [c.replace(',','') for c in observed]!=target:errors.append(f'{e["run_id"]} report cells mismatch: {observed} != {target}')
    missing_rows=[e['run_id'] for e in ex if e['run_id'] not in md]
    if missing_rows:errors.append('report missing runs: '+','.join(missing_rows))
    return {'checks':checks,'runs':len(ex),'conditions':sum(len(e['conditions']) for e in ex),'expected_outcomes':dict(collections.Counter(e['outcome'] for e in ex)),'errors':errors,'passed':not errors}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('who');p.add_argument('case');p.add_argument('--result');p.add_argument('--report');p.add_argument('--input');p.add_argument('--repaired',action='store_true');a=p.parse_args()
    base=OUT/a.who
    result=Path(a.result) if a.result else base/'out'/f'verdicts_{a.case}.json'
    report=Path(a.report) if a.report else base/'out'/f'report_{a.case}.md'
    inp=Path(a.input) if a.input else base/('input_base_snapshot' if a.case=='base' and (base/'input_base_snapshot').exists() else 'input')
    value=verify(inp,result,report,a.repaired)
    value['input_root']=str(inp)
    (OUT/'runs'/f'verify_{a.who}_{a.case}.json').write_text(json.dumps(value,ensure_ascii=False,indent=2))
    print(json.dumps(value,ensure_ascii=False)[:10000]);raise SystemExit(0 if value['passed'] else 1)
