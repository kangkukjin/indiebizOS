import sqlite3, json, sys
ep=int(sys.argv[1]); db=sqlite3.connect("file:/Users/kangkukjin/Desktop/AI/indiebizOS/data/world_pulse.db?mode=ro",uri=True)
rows=db.execute("select event_seq,ts,kind,data from trajectory_event where episode_id=? order by run_id,event_seq",(ep,)).fetchall()
json.dump([{"seq":s,"ts":t,"kind":k,"data":json.loads(d)} for s,t,k,d in rows],open(f"harness/agent_trace_{ep}.json","w"),ensure_ascii=False)
from collections import Counter
print("events",len(rows),Counter(k for _,_,k,_ in rows).most_common(40))
use=Counter(); byrole={}
for s,t,k,d in rows:
    d=json.loads(d)
    if k=="model.usage" and d.get("accounting")=="billable_usage":
        role=d.get("role") or d.get("purpose") or "?"
        b=byrole.setdefault(role,Counter())
        for f in ("input_tokens","output_tokens","cache_read_tokens","cache_creation_tokens","input","output","cache_read","cache_create"):
            if isinstance(d.get(f),(int,float)): b[f]+=d[f]; use[f]+=d[f]
        b["calls"]+=1
print("usage",dict(use)); print({r:dict(c) for r,c in byrole.items()})
n=0
for s,t,k,d in rows:
    d=json.loads(d)
    if k=="supervision.tool.started":
        n+=1; a=d.get("input") or d.get("args") or d
        code=(a.get("code") if isinstance(a,dict) else None)
        print(f"\n#{n} seq{s} {t[11:19]} {d.get('tool') or d.get('name')}", json.dumps({kk:(vv if kk!='code' else '…') for kk,vv in (a.items() if isinstance(a,dict) else [])},ensure_ascii=False)[:300])
        if code: print("   CODE:", code[:int(sys.argv[2]) if len(sys.argv)>2 else 500].replace("\n","\n   "))
    if k=="supervision.tool.finished":
        print(f"   -> seq{s} {t[11:19]}", json.dumps(d,ensure_ascii=False)[:420])
    if k in ("context.compacted","recall.presented","recall.used","supervision.cost.summary") or k.startswith("evaluation") or "eval" in k or "verdict" in k:
        print(f"** seq{s} {t[11:19]} {k}", json.dumps(d,ensure_ascii=False)[:500])
