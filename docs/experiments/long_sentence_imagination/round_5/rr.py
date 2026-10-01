import json,subprocess
def rr(rid,path,off=0,lim=60000):
    p=subprocess.run(['curl','-sS','-X','POST','http://127.0.0.1:8765/ibl/execute','-H','Content-Type: application/json','--data-binary','@-'],input=json.dumps({'code':'','edition':2,'project_id':'컨텐츠','origin':'training','agent_id':'LSI5_trainer','task_id':'LSI5_task','read_result':{'id':rid,'path':path,'offset':off,'limit':lim}}),text=True,capture_output=True)
    return json.loads(p.stdout)
def rr_all(rid,path):
    t='';off=0
    while True:
        r=rr(rid,path,off)
        if 'text' not in r: raise SystemExit(json.dumps(r,ensure_ascii=False)[:500])
        t+=r['text']; nr=r.get('next_read')
        if not nr: return t
        off=nr['offset']
