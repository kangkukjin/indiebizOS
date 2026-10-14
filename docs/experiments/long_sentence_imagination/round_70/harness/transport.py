"""HTTP transport, evidence preservation and summaries only; no task logic."""
import argparse
import json
import time
import urllib.request
import urllib.error
from pathlib import Path

ROOT=Path(__file__).resolve().parents[5]
OUT=ROOT/'outputs/long_sentence_imagination/2026-10-15_70회차'

def main():
    p=argparse.ArgumentParser();p.add_argument('label');p.add_argument('request')
    p.add_argument('--endpoint',default='/ibl/execute');a=p.parse_args()
    payload=json.loads(Path(a.request).read_text()) if a.request!='-' else None
    start=time.time()
    req=urllib.request.Request('http://127.0.0.1:8765'+a.endpoint,
        data=json.dumps(payload,ensure_ascii=False).encode() if payload is not None else None,
        headers={'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=1200) as r: result=json.load(r)
    except urllib.error.HTTPError as e: result={'http_status':e.code,'body':e.read().decode()}
    record={'request':payload,'endpoint':a.endpoint,'started':start,'ended':time.time(),'response':result}
    (OUT/'runs'/f'{a.label}.json').write_text(json.dumps(record,ensure_ascii=False,indent=2))
    print(json.dumps({'label':a.label,'elapsed':round(time.time()-start,3),
        'response':{k:result[k] for k in ('success','value','error','issues','warnings','status','state','task_id','status_url','run_status','result') if k in result}},ensure_ascii=False)[:9000])

if __name__=='__main__':main()
