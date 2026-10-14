"""Loopback warehouse protocol fixture; no credentials or public publishing."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, quote
from prepare import HERE, OUT, BASE

DATA=json.loads((HERE/'fixtures/notices.json').read_text())
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        p=urlparse(self.path); parts=p.path.strip('/').split('/')
        status=200; value=None
        if len(parts)<4 or parts[1] not in DATA or parts[2] not in 'abc':
            status=404; value={'error':'not found'}
        else:
            who,phase,wh,op=parts[:4]
            rows=DATA[phase][wh]
            if phase=='variant' and wh=='b':
                status=503; value={'error':'synthetic warehouse unavailable'}
            elif op=='manifest':
                files=[]
                for row in rows:
                    name=row['event_id']+'.json'
                    content=json.dumps(row,ensure_ascii=False).encode()
                    files.append({'name':name,'path':name,'size':len(content),'bytes':len(content),
                                  'mtime':1791936000+(3600 if row['updated_at'].startswith('2026-10-15') else 0),
                                  'url':f'{BASE}/{who}/{phase}/{wh}/f?path={quote(name)}','type':'file'})
                value={'title':f'합성 이웃 {wh}','files':files,'total':len(files),'level':0}
            elif op=='f':
                name=parse_qs(p.query).get('path',[''])[0]
                value=next((r for r in rows if r['event_id']+'.json'==name),None)
                if value is None: status=404; value={'error':'missing file'}
            else: status=404; value={'error':'not found'}
        raw=json.dumps(value,ensure_ascii=False).encode()
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        with (OUT/'http.jsonl').open('a') as f:
            f.write(json.dumps({'path':self.path,'status':status})+'\n')
    def log_message(self,*args): pass

if __name__=='__main__':
    print(f'Warehouse fixture {BASE}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',8876),Handler).serve_forever()
