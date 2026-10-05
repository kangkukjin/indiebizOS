import os, sys, time, json, csv, cProfile, pstats, io, tempfile
# 격리 실행: 상태 폴더는 임시(INDIEBIZ_REPRO_STATE 로 바꿀 수 있음), 백엔드는 이 파일 위치로 찾는다 — 어느 cwd 에서나 돈다.
S=os.environ.get("INDIEBIZ_REPRO_STATE") or tempfile.mkdtemp(prefix="lsi18_"); R="/Users/kangkukjin/Desktop/AI/indiebizOS/outputs/long_sentence_imagination/2026-10-05_18회차"
os.environ["INDIEBIZ_RUNTIME_STATE_DIR"]=S+"/state"; os.environ["INDIEBIZ_RECALL_INDEX_DIR"]=S+"/state/recall_index"
sys.path.insert(0,os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","..","..","..","..","backend"))
import boot_paths
from ibl_v2_entry import handle_request
ex={e["project"] for e in json.load(open(R+"/harness/expected_base.json"))["excluded"] if e["reason"]!="cycle"}
ta=list(csv.DictReader(open(R+"/inputs/tasks_a.csv",encoding="utf-8")))+json.load(open(R+"/inputs/tasks_b.json",encoding="utf-8"))
tasks=[{"task":t["id"],"project":t["project"],"owner":t["owner"],"dur":int(float(t["duration"]))} for t in ta if t["project"] not in ex]
seen=set(); deps=[]
for d in csv.DictReader(open(R+"/inputs/deps.csv",encoding="utf-8")):
    k=(d["task"],d["depends_on"])
    if k in seen or d["project"] in ex: continue
    seen.add(k); deps.append(d)
src=open(R+"/drafts/p2_v0.ibl",encoding="utf-8").read()
code=src.split("[def:지연분류]")[0].replace("[def:지연읽기]","[def:지연읽기x]")+'$r=[fn:일정]{prepared:$prepared,extra:[]}\nreturn $r.summary\n'
prepared={"task_count":2400,"project_count":60,"dep_count_raw":3806,"dep_count_unique":3799,"pre_excluded":[{"project":p,"reason":"x","detail_count":1} for p in sorted(ex)],"tasks":tasks,"deps":deps}
req={"code":code,"edition":2,"inputs":{"prepared":prepared},"budget":{"steps":1000000,"rows":100000}}
handle_request({"code":"#!ibl edition=2\nreturn 1","edition":2}, project_path=S+"/proj", agent_id="prof")  # 레지스트리 예열
t=time.time(); pr=cProfile.Profile(); pr.enable()
r=handle_request(req, project_path=S+"/proj", agent_id="prof")
pr.disable(); dt=time.time()-t
print("elapsed(profiled)",round(dt,2),(r or {}).get("success"),(r or {}).get("value"),(r or {}).get("usage",{}).get("steps"),str((r or {}).get("error"))[:400])
b=io.StringIO(); st=pstats.Stats(pr,stream=b); st.sort_stats("tottime"); st.print_stats(28)
print("\n".join(l[:170] for l in b.getvalue().splitlines() if "/" in l or "ncalls" in l or "{" in l))
b=io.StringIO(); st=pstats.Stats(pr,stream=b); st.sort_stats("cumulative"); st.print_stats("backend/|data/packages",45)
print("\n".join(l[:170].replace("/Users/kangkukjin/Desktop/AI/indiebizOS/","") for l in b.getvalue().splitlines() if "/" in l or "ncalls" in l))
t=time.time(); r=handle_request(req, project_path=S+"/proj", agent_id="prof"); print("elapsed(unprofiled)",round(time.time()-t,2))
