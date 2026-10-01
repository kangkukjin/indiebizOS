"""P1→P2→P3 를 이어 실행. usage: chain.py <label> <input_dir> <p1.ibl> <p2.ibl> <p3.ibl> [extra_p2_json]"""
import json, subprocess, sys, time
from pathlib import Path
HERE=Path(__file__).resolve().parent
label,indir,p1,p2,p3=sys.argv[1:6]; extra_p2=json.loads(sys.argv[6]) if len(sys.argv)>6 else {}
def post(payload):
    subprocess.run([str(HERE/'wait_active.sh')],capture_output=True)
    p=subprocess.run(['curl','-sS','--max-time','400','-X','POST','http://127.0.0.1:8765/ibl/execute','-H','Content-Type: application/json','--data-binary','@-'],input=json.dumps(payload),text=True,capture_output=True,check=True)
    return json.loads(p.stdout)
def run(name,code_file,inputs,extra=None):
    payload=dict(code=Path(code_file).read_text(),edition=2,project_id='컨텐츠',origin='training',agent_id='LSI6_trainer',task_id='LSI6_task',inputs=inputs); payload.update(extra or {})
    t=time.time(); r=post(payload); dt=time.time()-t
    (HERE/'runs'/f'{label}_{name}.json').write_text(json.dumps({'request':payload,'elapsed_s':round(dt,2),'response':r},ensure_ascii=False,indent=1))
    u=r.get('usage') or {}
    print(f"[{name}] success={r.get('success')} src_complete={r.get('source_complete')} {dt:.1f}s steps={u.get('steps')} model={(u.get('model') or {}).get('requests')} err={(r.get('error') or r.get('detail') or '')[:200]}")
    if r.get('continuation'): print('   continuation:',json.dumps(r['continuation'],ensure_ascii=False)[:300])
    return r
R=str(HERE)
r1=run('p1',p1,{"폴더":f"{indir}/ledger","규칙":f"{indir}/rules.json"})
if not r1.get('success'): sys.exit(1)
v=r1['value']; ref1=r1['result_ref']['id']
print('   파일상태:',[(f['파일'],f['상태'],f['행수'],f['경로']) for f in v['파일상태']]); print('   금액오류행:',v['금액오류행']); print('   행수',v['행수'],'가게수',v['가게수'],'AI',len(v['AI분류']))
r2=run('p2',p2,{"자료":{"$ref":ref1},"고정":f"{indir}/fixed.json",**extra_p2.get('inputs',{})},{k:v for k,v in extra_p2.items() if k!='inputs'})
if not r2.get('success'): sys.exit(1)
v2=r2['value']; ref2=r2['result_ref']['id']
print('   총지출',v2['총지출'],'환불합',v2['환불합'],'종류별',v2['종류별'])
r3=run('p3',p3,{"분석":{"$ref":ref2},"파일상태":{"$ref":ref1,"path":["value","파일상태"]},"AI분류":{"$ref":ref1,"path":["value","AI분류"]},"행수":v['행수'],"가게수":v['가게수'],"보고서":f"{R}/out/report_{label}.md","목록":f"{R}/out/anomalies_{label}.json"})
if r3.get('success'): print('   P3 value:',json.dumps({k:r3['value'][k] for k in ('보고일치','목록일치','이상수')},ensure_ascii=False))
