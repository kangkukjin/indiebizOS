import json, subprocess, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
def post(payload):
    p = subprocess.run(['curl','-sS','--max-time','400','-X','POST','http://127.0.0.1:8765/ibl/execute',
        '-H','Content-Type: application/json','--data-binary','@-'], input=json.dumps(payload), text=True, capture_output=True, check=True)
    return json.loads(p.stdout)
def main():
    # usage: ibl.py <label> <file.ibl|-> [--check] [--describe a,b] [--extra json]
    label = sys.argv[1]; src = sys.argv[2]
    code = '' if src == '-' else Path(src).read_text()
    payload = dict(code=code, edition=2, project_id='컨텐츠', origin='training', agent_id='LSI3_trainer', task_id='LSI3_task')
    a = sys.argv[3:]
    if '--check' in a: payload['check'] = True
    if '--describe' in a: payload['describe'] = a[a.index('--describe')+1].split(',')
    if '--extra' in a: payload.update(json.loads(a[a.index('--extra')+1]))
    t=time.time(); r = post(payload); dt=time.time()-t
    out = HERE/'runs'/f'{label}.json'
    out.write_text(json.dumps({'request':payload,'elapsed_s':round(dt,2),'response':r}, ensure_ascii=False, indent=1))
    print(f'elapsed {dt:.1f}s -> {out.name}')
    print(json.dumps(r, ensure_ascii=False, indent=1)[:int(dict(zip(a,a[1:])).get('--max','6000'))])
main()
