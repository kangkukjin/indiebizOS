"""Detached real processes: streaming, stdin dedup, EOF and restart reconnect."""
import json
import time
import sys
import shlex
import pytest
from coding_store import CodingStore
from process_sessions import start, query
from test_situation_evidence import active  # noqa: F401


def test_repair_server_survives_receipt_and_keeps_environment_private(tmp_path, monkeypatch):
    from pathlib import Path
    from code_analysis_scope import bind
    from repair_process import run
    from process_sessions import quiesce_workspace, directory
    repo = Path(__file__).resolve().parents[1]
    workspace = tmp_path / 'project'
    workspace.mkdir()
    db = CodingStore(tmp_path / 'store')
    execution = {'root': str(workspace), 'cwd': str(workspace), 'body': False,
                 'repo': str(repo), 'key': 'test', 'cancel_path': str(tmp_path / 'cancel')}
    monkeypatch.setenv('TEST_API_KEY', 'fixture-private-value')
    code = '''import os
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
assert os.environ['TEST_API_KEY'] == 'fixture-private-value'
Path(os.environ['XDG_CONFIG_HOME']).mkdir(parents=True)
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  self.send_response(200); self.end_headers(); self.wfile.write(b'ALIVE')
server=HTTPServer(('127.0.0.1',0),Handler)
print(server.server_port,flush=True)
server.serve_forever()
'''
    script = workspace / 'server.py'
    script.write_text(code)
    with bind(workspace, writable=True, execution=execution):
        receipt = start(shlex.join([sys.executable, '-u', str(script)]), workspace, db=db, yield_ms=1000)
        tid = receipt['task_ref']['task_id']
        try:
            assert receipt['state'] == 'running', receipt
            port = int(''.join(row['text'] for row in receipt['output']).strip())
            client = f'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:{port}").read().decode())'
            result = run([sys.executable, '-c', client], workspace, body=False, timeout=10)
            assert result.returncode == 0 and result.stdout.strip() == 'ALIVE', result.stderr
            assert 'fixture-private-value' not in (directory(tid, db) / 'session.json').read_text()
        finally:
            quiesce_workspace(workspace, db=db)
        assert query(tid, db=db)['cleanup']['confirmed']


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


# ── 몸이 쥐는 명령(hold) — docs/BODY_HELD_COMMANDS_DESIGN_2026_11_17.md ──

def _cancel(tid, db):
    value = query(tid, db=db)
    if value['state'] in ('queued', 'running'):
        query(tid, db=db, op='control', action='cancel', request_id='test-cancel', generation=value['generation'])
        deadline = time.time() + 8
        while value['state'] in ('queued', 'running') and time.time() < deadline:
            value = query(tid, db=db, wait_ms=200)
    return value


def test_hold_returns_a_finished_command_with_streams_and_exit_code(tmp_path):
    from process_sessions import hold
    db = CodingStore(tmp_path / 'store')
    done = hold('echo out; echo err >&2; exit 3', tmp_path, db=db, timeout=10, shell='sh')
    assert done['state'] == 'failed' and done['exit_code'] == 3
    assert done['stdout'] == 'out\n' and done['stderr'] == 'err\n'
    assert 'signs' not in done  # 끝난 명령에는 살아 있다는 신호가 없다


def test_hold_comes_back_without_killing_and_reports_life_signs(tmp_path):
    """제한 시간이 지나면 기다리던 쪽만 돌아온다. 명령은 계속 돌고, 일하는 중인지 서 있는지를 가를 사실이 온다."""
    from process_sessions import hold
    db = CodingStore(tmp_path / 'store')
    idle = hold(f'{shlex.quote(sys.executable)} -u -c "import time; print(1, flush=True); time.sleep(60)"',
                tmp_path, db=db, timeout=3, shell='sh')
    busy = hold(f'{shlex.quote(sys.executable)} -c "\nwhile True: pass"', tmp_path, db=db, timeout=3, shell='sh')
    try:
        assert idle['state'] == 'running' and idle['exit_code'] is None and idle['stdout'] == '1\n'
        assert idle['task_ref']['kind'] == 'process'
        signs = idle['signs']
        assert signs['stdin'] == 'closed' and signs['output_seen'] is True
        assert 2 <= signs['quiet_s'] <= 10 and signs['running_s'] >= 2
        assert any('python' in name.lower() for name in signs['processes'])
        assert signs['cpu_s'] < 1                                    # 자고 있는 프로세스는 CPU를 쓰지 않았다
        assert busy['state'] == 'running' and busy['signs']['output_seen'] is False
        assert busy['signs']['cpu_s'] > 1 and busy['signs']['cpu_quiet_s'] < 3   # 도는 프로세스는 방금까지 썼다
        # 돌아온 뒤에도 같은 손잡이로 이어서 본다
        again = query(idle['task_ref']['task_id'], db=db, cursor=idle['cursor'], wait_ms=200)
        assert again['state'] == 'running' and again['signs']['running_s'] >= signs['running_s']
    finally:
        assert _cancel(idle['task_ref']['task_id'], db)['state'] == 'cancelled'
        assert _cancel(busy['task_ref']['task_id'], db)['state'] == 'cancelled'


def test_held_command_starts_with_input_closed(tmp_path):
    """에피소드 6178의 명령 꼴: 잘못 든 `cat`이 열린 입력을 기다리며 섰다. 닫고 시작하면 바로 지나간다."""
    from process_sessions import hold
    db = CodingStore(tmp_path / 'store')
    done = hold('cat >> /dev/null; echo passed', tmp_path, db=db, timeout=10, shell='sh')
    assert done['state'] == 'succeeded' and done['stdout'] == 'passed\n'
    # 입력을 주고받을 세션은 지금처럼 열려 있다
    live = start('cat', tmp_path, db=db, shell='sh', yield_ms=300)
    try:
        assert live['state'] == 'running' and live['capabilities']['input'] is True
        assert query(live['task_ref']['task_id'], db=db)['signs']['stdin'] == 'open'
    finally:
        _cancel(live['task_ref']['task_id'], db)


def test_hold_uses_the_users_shell_path_when_asked(tmp_path, monkeypatch):
    import process_sessions
    db = CodingStore(tmp_path / 'store')
    monkeypatch.setattr(process_sessions, '_USER_SHELL', {'value': ('sh', '/indiebiz-user-bin:/usr/bin:/bin')})
    asked = process_sessions.hold('echo "$PATH"', tmp_path, db=db, timeout=10, user=True)
    plain = process_sessions.hold('echo "$PATH"', tmp_path, db=db, timeout=10, shell='sh')
    assert asked['stdout'].startswith('/indiebiz-user-bin:')
    assert '/indiebiz-user-bin' not in plain['stdout']


def test_held_commands_do_not_pile_up_records(tmp_path, monkeypatch):
    """명령마다 세션이 생기므로, 결과를 다 돌려준 세션은 곧바로 거두고 손잡이를 넘긴 세션은 수명 뒤에 거둔다."""
    import process_sessions
    db = CodingStore(tmp_path / 'store')
    done = process_sessions.hold('echo done', tmp_path, db=db, timeout=10, shell='sh')
    assert done['state'] == 'succeeded'
    assert db.list('process_session') == []
    assert not any((db.root / 'processes').iterdir())

    handed = process_sessions.hold(f'{shlex.quote(sys.executable)} -c "import time; time.sleep(60)"',
                                   tmp_path, db=db, timeout=1, shell='sh')
    tid = handed['task_ref']['task_id']
    assert handed['state'] == 'running' and [row['id'] for row in db.list('process_session')] == [tid]
    assert _cancel(tid, db)['state'] == 'cancelled'
    monkeypatch.setitem(process_sessions._SWEEP, 'at', 0.0)
    assert process_sessions._sweep(db) == 0                      # 방금 끝난 것은 아직 볼 수 있다
    assert [row['id'] for row in db.list('process_session')] == [tid]
    monkeypatch.setitem(process_sessions._SWEEP, 'at', 0.0)
    assert process_sessions._sweep(db, now=time.time() + 86400 + 60) == 1
    assert db.list('process_session') == [] and not (db.root / 'processes' / tid).exists()

    # 입력을 주고받는 세션(start)은 쓸지 않는다
    live = start('cat', tmp_path, db=db, shell='sh', yield_ms=200)
    try:
        monkeypatch.setitem(process_sessions._SWEEP, 'at', 0.0)
        assert process_sessions._sweep(db, now=time.time() + 86400 * 3) == 0
        assert [row['id'] for row in db.list('process_session')] == [live['task_ref']['task_id']]
    finally:
        _cancel(live['task_ref']['task_id'], db)
