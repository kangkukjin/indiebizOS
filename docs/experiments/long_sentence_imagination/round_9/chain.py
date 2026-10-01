"""P1→P2→P3 연쇄. usage: chain.py <label> <input_dir> <p1> <p2> <p3> [reuse_run_id_p1]"""
import json, subprocess, sys, time
from pathlib import Path
H=Path(__file__).resolve().parent; label,indir,p1,p2,p3=sys.argv[1:6]
def run(name,code,extra):
    payload=dict(code=Path(code).read_text(),edition=2,project_id='컨텐츠',origin='training',agent_id='LSI9_trainer',task_id='LSI9_task',**extra)
    t=time.time(); p=subprocess.run(['curl','-sS','--max-time','400','-X','POST','http://127.0.0.1:8765/ibl/execute','-H','Content-Type: application/json','--data-binary','@-'],input=json.dumps(payload),text=True,capture_output=True,check=True); r=json.loads(p.stdout); dt=time.time()-t
    (H/'runs'/f'{label}_{name}.json').write_text(json.dumps({'request':payload,'elapsed_s':round(dt,2),'response':r},ensure_ascii=False,indent=1))
    u=r.get('usage') or {}; print(f"[{name}] success={r.get('success')} src_complete={r.get('source_complete')} {dt:.1f}s steps={u.get('steps')} model={(u.get('model') or {}).get('requests')} reuse={json.dumps(r.get('reuse'),ensure_ascii=False)[:300]} err={(r.get('error') or '')[:300]}")
    return r
files=[f"orders_2025-0{m}.csv" for m in range(1,7)]+["carrier_A.csv","carrier_B.json","returns.csv","refunds.csv","sla.json"]
e1={"inputs":{"폴더":indir},"budget":{"steps":600000,"rows":60000}}
if len(sys.argv)>6: e1["reuse"]={"run_id":sys.argv[6]}
r1=run('p1',p1,e1)
if not r1.get('success'): sys.exit(1)
v=r1['value']; print('  ',v['행수'],[(f['파일'],f['상태']) for f in v['파일상태'] if f['상태']!='읽음'],v['오류행'])
r2=run('p2',p2,{"inputs":{"자료":{"$ref":r1['result_ref']['id']},"기대파일":files},"budget":{"steps":900000,"rows":90000}})
if not r2.get('success'): sys.exit(1)
v2=r2['value']; print('  ',v2['종류별'],v2['택배사표'],v2['지연건수'],v2['총매출'],v2['배송단서'])
r3=run('p3',p3,{"inputs":{"분석":{"$ref":r2['result_ref']['id']},"보고서":f"{H}/out/report_{label}.md","목록":f"{H}/out/issues_{label}.json"}})
print('  ',r3.get('value'))
