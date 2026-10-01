import json,subprocess,sys,re
rid=sys.argv[1]; out=sys.argv[2]
buf=[];off=0
for n in range(60):
    p=subprocess.run(['curl','-sS','-X','POST','http://127.0.0.1:8765/ibl/execute','-H','Content-Type: application/json','--data-binary','@-'],input=json.dumps({"code":"","edition":2,"project_id":"컨텐츠","origin":"training","agent_id":"LSI2_trainer","task_id":"LSI2_task","read_result":{"id":rid,"offset":off,"limit":60000}}),text=True,capture_output=True)
    r=json.loads(p.stdout); t=r.get('text','')
    if not t: print(r); break
    buf.append(t); off+=len(t)
    if off>=r.get('chars',0): break
s=''.join(buf); open(out,'w').write(s); print('chars',len(s))
d=json.loads(s)
def walk(v,pre,depth):
    if isinstance(v,dict) and depth<3:
        for k,x in v.items():
            L=len(json.dumps(x,ensure_ascii=False))
            if L>2000: print(pre+k, L); walk(x,pre+k+'.',depth+1)
walk(d,'',0)
print(sorted(set(re.findall(r'"(\w*(?:token|usage|cost|model)\w*)"',s)))[:40])
