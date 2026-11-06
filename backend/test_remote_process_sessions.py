"""Resident session control, byte replay and a real helper reconnect."""
import base64
import json
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
import uuid
import pytest
from coding_store import CodingStore
import remote_process_sessions as remote
import limb_keys
import device_registry


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(limb_keys, '_store_path', lambda: tmp_path / 'keys.json')
    monkeypatch.setattr(limb_keys, '_cache', None)
    monkeypatch.setenv('INDIEBIZ_RUNTIME_STATE_DIR', str(tmp_path))
    monkeypatch.setattr(device_registry, 'register', lambda *a, **k: None)
    db=CodingStore(tmp_path/'coding');monkeypatch.setattr(remote, '_store', lambda: CodingStore(db.root))
    rec=limb_keys.resident_enroll(limb_keys.resident_invite('process-test')['key'], uuid.uuid4().hex)
    limb_keys.resident_update(rec['device_id'], capabilities={'terminal':True,'process_session':1},last_seen=time.time())
    return rec,db


def test_remote_queue_no_replay_after_ambiguous_write(setup):
    rec,db=setup
    r=remote.start(rec['device_id'],'cat',request_id='one');ref=r['task_ref']
    params={'action':'input','text':'hello','generation':r['generation'],'request_id':'input'}
    assert remote.control(ref,params)['delivery']=='queued'
    assert len(remote.take(ref['task_id']))==1
    assert remote.control(ref,params)['delivery']=='delivery_unknown'
    assert remote.take(ref['task_id'])==[]
    remote.receive(ref['task_id'],{'type':'ack','request_id':'input','delivery':'delivered','bytes_written':5})
    assert remote.control(ref,params)['delivery']=='delivered'
    for _ in range(2):remote.receive(ref['task_id'],{'type':'output','offset':0,'data':base64.b64encode(b'hello').decode()})
    assert remote.status(ref)['output'][0]['text']=='hello'
    with pytest.raises(ValueError):remote.control(ref,{**params,'text':'different'})
    assert remote.start(rec['device_id'],'cat',request_id='one')['task_ref']==ref


@pytest.mark.system
def test_native_helper_reconnects_same_program(setup,tmp_path):
    import uvicorn
    from fastapi import FastAPI
    from api_remote_process import router
    rec,db=setup
    binary=Path(os.environ.get('INDIEBIZ_TEST_PROCESS_HELPER','/tmp/indiebiz-process-helper'))
    if not binary.is_file():pytest.skip('build helper with go build -o /tmp/indiebiz-process-helper')
    sock=socket.socket();sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    def server_start(sock):
        app=FastAPI();app.include_router(router)
        server=uvicorn.Server(uvicorn.Config(app,log_level='error',timeout_graceful_shutdown=1))
        thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
        end=time.time()+5
        while not server.started and time.time()<end:time.sleep(.02)
        return server,thread
    server,thread=server_start(sock)
    command="printf 'START:%s\\n' $$; cat"
    r=remote.start(rec['device_id'],command,cwd=str(tmp_path));ref=r['task_ref'];sid=ref['task_id'].removeprefix('remoteprocess_')
    spec=tmp_path/'spec.json'
    spec.write_text(json.dumps({'config':{'base':f'http://127.0.0.1:{port}','key':rec['key'],'installation_id':rec['registration']['installation_id']},
        'terminal_id':sid,'cols':100,'rows':30,'process_session':True,'cmd':command,'cwd':str(tmp_path)}))
    process=subprocess.Popen([str(binary),'--resident-terminal',str(spec)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    def wait_text(text):
        deadline=time.time()+10
        while time.time()<deadline:
            value=remote.status(ref)
            if text in ''.join(i['text'] for i in value['output']):return value
            time.sleep(.05)
        raise AssertionError((text,value))
    try:
        wait_text('START:');assert process.poll() is None
        server.should_exit=True;thread.join(5)
        assert process.poll() is None
        nextsock=socket.socket();nextsock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);nextsock.bind(('127.0.0.1',port))
        server,thread=server_start(nextsock)
        remote.control(ref,{'action':'input','text':'AFTER_RECONNECT','newline':True,'generation':r['generation'],'request_id':'after'})
        out=wait_text('AFTER_RECONNECT')
        assert ''.join(i['text'] for i in out['output']).count('START:')==1
        remote.control(ref,{'action':'cancel','generation':r['generation'],'request_id':'stop'})
        process.wait(timeout=10)
    finally:
        if process.poll() is None:
            process.stdin.close();process.wait(timeout=10)
        server.should_exit=True;thread.join(5)
