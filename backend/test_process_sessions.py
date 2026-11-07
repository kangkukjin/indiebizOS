"""Detached real processes: streaming, stdin dedup, EOF and restart reconnect."""
import json
import time
import sys
import shlex
import pytest
from coding_store import CodingStore
from process_sessions import start, query
from test_situation_evidence import active  # noqa: F401


def test_pipe_reconnect_input_eof_and_output(tmp_path):
    db = CodingStore(tmp_path / 'store')
    script = tmp_path / 'read.py'
    script.write_text("import sys\nprint('READY', flush=True)\nfor line in sys.stdin:\n print('OUT:'+line.strip(), flush=True)\n print('ERR:'+line.strip(), file=sys.stderr, flush=True)\n")
    r = start(f'{shlex.quote(sys.executable)} -u {shlex.quote(str(script))}', tmp_path,
              db=db, request_id='start', yield_ms=1000)
    tid, gen = r['task_ref']['task_id'], r['generation']
    assert r['state'] == 'running', r
    assert start(f'{shlex.quote(sys.executable)} -u {shlex.quote(str(script))}', tmp_path,
                 db=db, request_id='start')['task_ref']['task_id'] == tid
    args = dict(op='control', action='input', text='hello', newline=True, request_id='input1', generation=gen)
    try:
        assert query(tid, db=db, **args)['bytes_written'] == 6
        assert query(tid, db=CodingStore(db.root), **args)['cached']
        query(tid, db=db, op='control', action='eof', request_id='eof', generation=gen)
        deadline=time.time()+8
        while time.time()<deadline:
            out=query(tid, db=db, wait_ms=100)
            if out['state'] != 'running': break
        assert out['state'] == 'succeeded', out
        text=''.join(v['text'] for v in out['output'])
        assert text.count('OUT:hello') == 1 and text.count('ERR:hello') == 1
        assert {v['stream'] for v in out['output']} == {'stdout','stderr'}
        with pytest.raises(ValueError): query(tid, db=db, generation='wrong')
    finally:
        try: query(tid, db=db, op='control', action='cancel', request_id='cleanup')
        except ValueError: pass


def test_pty_resize_interrupt(tmp_path):
    db=CodingStore(tmp_path/'store')
    r=start('cat', tmp_path, io='pty', db=db, yield_ms=0)
    tid=r['task_ref']['task_id']
    try:
        assert r['capabilities']['resize']
        query(tid, db=db, op='control', action='resize', cols=100, rows=40, request_id='size')
        query(tid, db=db, op='control', action='input', text='PTY_OK', newline=True, request_id='in')
        out=query(tid, db=db, wait_ms=1000)
        assert 'PTY_OK' in ''.join(x['text'] for x in out['output'])
        query(tid, db=db, op='control', action='interrupt', request_id='int')
        deadline=time.time()+5
        while time.time()<deadline:
            out=query(tid, db=db)
            if out['state'] != 'running': break
            time.sleep(.05)
        assert out['state'] in ('failed', 'succeeded')
    finally:
        try: query(tid, db=db, op='control', action='cancel', request_id='cleanup')
        except ValueError: pass


def test_registered_script_and_ibl_controls(tmp_path, monkeypatch):
    from pathlib import Path
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    from thread_context import actor_context
    monkeypatch.setenv('INDIEBIZ_RUNTIME_STATE_DIR', str(tmp_path/'state'))
    # A fixture registry keeps the real script adapter while avoiding user definitions.
    registry=tmp_path/'state/scripts';registry.mkdir(parents=True)
    root=Path(__file__).resolve().parents[1]
    import yaml
    entries=yaml.safe_load((root/'data/scripts/registry.yaml').read_text())
    entry=entries['프로세스실행'];entry['file']=str(root/'data/scripts/process_control.py')
    (registry/'registry.yaml').write_text(yaml.safe_dump({'프로세스실행':entry},allow_unicode=True))
    inputs={'root':str(tmp_path)}
    code='''$r=[self:script]{op:"run",id:"프로세스실행",args:{command:"cat",cwd:$root,lifetime:"session",yield_ms:0}};
    $s=[self:task]{op:"status",ref:$r.task_ref};
    [self:task]{op:"control",ref:$r.task_ref,generation:get($s.progress,"generation"),request_id:"hello",action:"input",text:"IBL_PROCESS_OK",newline:true};
    [self:task]{op:"control",ref:$r.task_ref,generation:get($s.progress,"generation"),request_id:"end",action:"eof"};
    [self:task]{op:"wait",ref:$r.task_ref,timeout:10}'''
    plan=compile_program(code,load_registry(str(root)),inputs)
    assert not plan.issues,plan.issues
    with actor_context(origin='training'):
        result=Runtime(plan,inputs).run()
    assert result['success'],result.get('diagnostic')
    assert 'IBL_PROCESS_OK' in str(result['value'])


@pytest.mark.system
def test_backend_owner_exit_keeps_same_session(tmp_path):
    import os
    import subprocess
    from pathlib import Path
    from restart_process import ProcessAdapter, identity, signal_owned
    root = Path(__file__).resolve().parents[1]
    db = CodingStore(tmp_path/'state')
    ready = tmp_path/'ready.json'
    code = '''import sys,json,time
sys.path.insert(0,sys.argv[1]);import boot_paths
import runtime_work
runtime_work.install('process-session-test').gate('ACTIVE')
runtime_work.install_worker_tracking()
from process_sessions import start
from coding_store import CodingStore
with runtime_work.scope('test-start'):
 r=start('cat',sys.argv[2],db=CodingStore(sys.argv[3]),lifetime='session',yield_ms=0)
with open(sys.argv[4],'w') as f:json.dump(r,f)
assert not runtime_work.registry().snapshot()['active_children']
time.sleep(60)
'''
    host = subprocess.Popen([sys.executable,'-c',code,str(root/'backend'),str(tmp_path),str(db.root),str(ready)],
                            env={**os.environ,'INDIEBIZ_BASE_PATH':str(root)})
    ref = None
    try:
        deadline=time.time()+15
        while time.time()<deadline and not ready.exists():
            assert host.poll() is None
            time.sleep(.05)
        ref=json.loads(ready.read_text())
        adapter=ProcessAdapter(root,root)
        members=adapter.tree(identity(host.pid))
        assert [m['pid'] for m in members]==[host.pid], members
        for member in members:signal_owned(member,force=True)
        host.wait(timeout=5)
        tid=ref['task_ref']['task_id']
        query(tid,db=CodingStore(db.root),op='control',action='input',text='AFTER_HOST_EXIT',newline=True,request_id='again',actor='ui')
        out=query(tid,db=db,wait_ms=1000)
        assert 'AFTER_HOST_EXIT' in ''.join(x['text'] for x in out['output'])
        # Cancellation must remain possible while another actor owns the input lease.
        query(tid,db=db,op='control',action='cancel',request_id='stop',actor='ai')
    finally:
        if host.poll() is None:host.kill();host.wait()
        if ref:
            try:query(ref['task_ref']['task_id'],db=db,op='control',action='cancel',request_id='cleanup')
            except ValueError:pass


def test_session_shell_identity_and_execution_diagnostics(active, tmp_path):
    from api_supervision import situation_context
    db = CodingStore(tmp_path / 'store')
    r = start('echo session-error >&2; exit 7', tmp_path, db=db, shell='sh', request_id='dialect', yield_ms=1000)
    tid = r['task_ref']['task_id']
    deadline = time.time() + 5
    while r['state'] in ('queued', 'running') and time.time() < deadline:
        r = query(tid, db=db, wait_ms=100)
    assert r['exit_code'] == 7
    assert r['diagnostics']['phase'] == 'execution'
    assert 'SHELL_EXIT_NONZERO' in situation_context('executor', 'situation-test')['context']
    with pytest.raises(ValueError, match='request_id'):
        start('echo session-error >&2; exit 7', tmp_path, db=db, shell='bash', request_id='dialect')
