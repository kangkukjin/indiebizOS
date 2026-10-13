"""Public test application primitives; no setup/orchestration/recovery policy."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def write(path, value):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def event(kind, **kwargs):
    with (ROOT/'events.jsonl').open('a', encoding='utf-8') as f:
        f.write(json.dumps({'kind':kind,'time':time.time(),**kwargs},ensure_ascii=False)+'\n')

def main():
    p=argparse.ArgumentParser()
    p.add_argument('op',choices=['hash','patch','process','port','start','serve','health','stop','snapshot','restore'])
    p.add_argument('--expected');p.add_argument('--factor',type=int);p.add_argument('--output')
    p.add_argument('--port',type=int);p.add_argument('--nonce',default='service')
    p.add_argument('--ttl',type=int,default=180);p.add_argument('--empty',action='store_true')
    p.add_argument('--file',default='settings.json')
    a=p.parse_args();os.chdir(ROOT)
    if a.op=='hash':
        print(digest(a.file));return
    if a.op=='patch':
        before=Path('settings.json').read_bytes();old=hashlib.sha256(before).hexdigest()
        if old!=a.expected:
            event('conflict',expected=a.expected,actual=old)
            print(json.dumps({'status':'conflict','actual':old}));sys.exit(23)
        data=json.loads(before.decode('utf-8'))
        backup=ROOT/'data/_backups/2026-10-14_tv1_setup'/f'{old}.json'
        backup.parent.mkdir(parents=True,exist_ok=True)
        if not backup.exists():backup.write_bytes(before)
        data.update(factor=a.factor,output=a.output)
        write('settings.json',data);event('patch',before=old,after=digest('settings.json'))
        print(digest('settings.json'));return
    if a.op=='process':
        cfg=read('settings.json');rows=[] if a.empty else read('input/sample.json')
        result=[{**r,'result':r['value']*cfg['factor']} for r in rows]
        out=Path(cfg['output'])/('empty.json' if a.empty else 'result.json')
        write(out,result);event('process',output=str(out),factor=cfg['factor'],count=len(result))
        print(json.dumps({'path':str(out),'count':len(result),'total':sum(r['result'] for r in result)}));return
    if a.op=='port':
        s=socket.socket()
        try:s.bind(('127.0.0.1',a.port))
        except OSError:print('occupied');sys.exit(24)
        finally:s.close()
        print('free');return
    if a.op=='serve':
        info={'nonce':a.nonce,'pid':os.getpid(),'root':str(ROOT),'port':a.port,'started':time.time()}
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                if self.path not in ('/health','/stop/'+a.nonce):self.send_error(404);return
                body=json.dumps(info).encode();self.send_response(200);self.end_headers();self.wfile.write(body)
                if self.path.startswith('/stop/'):
                    threading.Thread(target=self.server.shutdown,daemon=True).start()
        server=ThreadingHTTPServer(('127.0.0.1',a.port),Handler)
        write('service-'+a.nonce+'.json',info)
        timer=threading.Timer(a.ttl,server.shutdown);timer.daemon=True;timer.start()
        event('service_start',**info)
        try:server.serve_forever(poll_interval=.1)
        finally:server.server_close();timer.cancel();event('service_stop',**info)
        return
    if a.op=='start':
        log=open('service-'+a.nonce+'.log','ab')
        launched=time.time()
        proc=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'serve','--port',str(a.port),'--nonce',a.nonce,'--ttl',str(a.ttl)],stdin=subprocess.DEVNULL,stdout=log,stderr=log,creationflags=0x00000008 if os.name=='nt' else 0,start_new_session=os.name!='nt')
        log.close()
        for _ in range(50):
            if proc.poll() is not None:sys.exit(proc.returncode or 25)
            f=Path('service-'+a.nonce+'.json')
            if f.exists():
                data=read(f)
                if data['started']>=launched and data['nonce']==a.nonce:
                    observed=json.load(urllib.request.urlopen(f'http://127.0.0.1:{a.port}/health',timeout=2))
                    if observed==data:
                        print(json.dumps({**data,'launcher_pid':proc.pid}));return
            time.sleep(.1)
        print('startup unconfirmed');sys.exit(26)
    if a.op in ('health','stop'):
        saved=read('service-'+a.nonce+'.json')
        url=f"http://127.0.0.1:{saved['port']}"
        data=json.load(urllib.request.urlopen(url+'/health',timeout=4))
        assert data==saved, (data,saved)
        if a.op=='stop':
            urllib.request.urlopen(url+'/stop/'+a.nonce,timeout=4).read()
            for _ in range(50):
                s=socket.socket();s.settimeout(.2)
                try:s.connect(('127.0.0.1',saved['port']))
                except OSError:print(json.dumps({'stopped':True,**saved}));return
                finally:s.close()
                time.sleep(.1)
            sys.exit(27)
        print(json.dumps(data));return
    if a.op=='restore':
        # Restore into a NEW verification copy only, never live settings.
        source=Path('data/_backups/2026-10-14_tv1_setup')/(a.expected+'.json')
        target=Path('restored-copy.json');target.write_bytes(source.read_bytes())
        assert digest(target)==a.expected;print(digest(target));return
    if a.op=='snapshot':
        files={str(x.relative_to(ROOT)).replace('\\','/'):digest(x) for base in ['input','protected','out-a','out-b'] for x in (ROOT/base).rglob('*') if x.is_file()}
        print(json.dumps({'settings':read('settings.json'),'sha256':digest('settings.json'),'files':files,'python':sys.executable,'version':sys.version,'events':[json.loads(l) for l in Path('events.jsonl').read_text(encoding='utf-8').splitlines()] if Path('events.jsonl').exists() else []},ensure_ascii=False))

if __name__=='__main__':main()
