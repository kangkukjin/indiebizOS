"""P1→P2→P3 연쇄. usage: chain.py <label> <input_dir> <달> <p1> <p2> <p3>"""
import json, subprocess, sys, time
from pathlib import Path
H=Path(__file__).resolve().parent; label,indir,month,p1,p2,p3=sys.argv[1:7]
def run(name,code,extra):
    payload=dict(code=Path(code).read_text(),edition=2,project_id='컨텐츠',origin='training',agent_id='LSI10_trainer',task_id='LSI10_task',**extra)
    t=time.time(); p=subprocess.run(['curl','-sS','--max-time','400','-X','POST','http://127.0.0.1:8765/ibl/execute','-H','Content-Type: application/json','--data-binary','@-'],input=json.dumps(payload),text=True,capture_output=True,check=True); r=json.loads(p.stdout); dt=time.time()-t
    (H/'runs'/f'{label}_{name}.json').write_text(json.dumps({'request':payload,'elapsed_s':round(dt,2),'response':r},ensure_ascii=False,indent=1))
    u=r.get('usage') or {}; print(f"[{name}] success={r.get('success')} src_complete={r.get('source_complete')} {dt:.1f}s steps={u.get('steps')} model={(u.get('model') or {}).get('requests')} err={(r.get('error') or '')[:400]}")
    for n in (r.get('execution_notes') or [])[:3]: print('   note:',n['warning'][:200],n['location'].get('line'))
    return r
r1=run('p1',p1,{"inputs":{"폴더":indir},"budget":{"steps":600000,"rows":60000}})
if not r1.get('success'): sys.exit(1)
print('  ',[(f['파일'],f['상태'],f['행수'],f['오류']) for f in r1['value']['파일상태'] if f['상태']!='읽음' or 'week' in f['파일']])
r2=run('p2',p2,{"inputs":{"자료":{"$ref":r1['result_ref']['id']}},"budget":{"steps":900000,"rows":90000}})
if not r2.get('success'): sys.exit(1)
v=r2['value']; print('  ',v['종류별'],v['출결행수'],v['수납합계'],v['출결단서'],v['유형별'])
r3=run('p3',p3,{"inputs":{"분석":{"$ref":r2['result_ref']['id']},"달":month,"보고서":f"{H}/out/report_{label}.md","목록":f"{H}/out/issues_{label}.json"}})
print('  ',r3.get('value'))
