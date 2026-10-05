import json, sys, time, urllib.request
from pathlib import Path
request_path, output_path = map(Path,sys.argv[1:3])
payload=json.loads(request_path.read_text(encoding='utf-8'))
start=time.time()
req=urllib.request.Request('http://127.0.0.1:8765/system-ai/chat',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'},method='POST')
try:
    with urllib.request.urlopen(req,timeout=2500) as response:
        result=json.load(response)
    output_path.write_text(json.dumps({'elapsed_seconds':time.time()-start,'response':result},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'saved':str(output_path),'elapsed_seconds':time.time()-start},ensure_ascii=False),flush=True)
except Exception as e:
    output_path.write_text(json.dumps({'elapsed_seconds':time.time()-start,'transport_error':str(e)},ensure_ascii=False),encoding='utf-8')
    print(type(e).__name__,str(e),flush=True)
    raise
