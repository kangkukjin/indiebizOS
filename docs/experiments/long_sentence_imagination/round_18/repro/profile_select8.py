import os, sys, time, json, cProfile, pstats
S=os.path.dirname(os.path.abspath(__file__))
os.environ["INDIEBIZ_RUNTIME_STATE_DIR"]=S+"/state"; os.environ["INDIEBIZ_RECALL_INDEX_DIR"]=S+"/state/recall_index"
sys.path.insert(0,os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","..","..","..","..","backend"))
import boot_paths
from ibl_v2_entry import handle_request
rows=[{"task":f"P{i//40:03d}-T{i%40:02d}","project":f"P{i//40:03d}","owner":"팀가","dur":i%15+1} for i in range(2040)]
code=sys.argv[1]
req={"code":code,"edition":2,"inputs":{"rows":rows},"budget":{"steps":1000000,"rows":100000}}
t=time.time(); pr=cProfile.Profile(); pr.enable()
r=handle_request(req, project_path=S+"/proj", agent_id="prof")
pr.disable(); dt=time.time()-t
print("elapsed",round(dt,2),"success",(r or {}).get("success"),"value",str((r or {}).get("value"))[:80],(r or {}).get("usage",{}).get("steps"), str((r or {}).get("error"))[:300])
st=pstats.Stats(pr); st.sort_stats("cumulative"); 
import io; b=io.StringIO(); st.stream=b; st.print_stats(int(sys.argv[2]) if len(sys.argv)>2 else 45); 
print("\n".join(l[:210] for l in b.getvalue().splitlines()[4:]))
