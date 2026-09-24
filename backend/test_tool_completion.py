"""Waiting consumes executor work, never extra model turns or submissions."""
import boot_paths  # noqa: F401
import asyncio
import json
import threading
from concurrent.futures import Future
from types import SimpleNamespace
import pytest
from tool_completion import (await_completion, CompletionState, DeferredToolResult,
                             CompletionWaitError)


@pytest.mark.parametrize('duration', [1, 30, 300, 800])
def test_duration_stays_inside_completion_boundary(duration):
    now = [0.0]
    events = []
    def poll(interval):
        now[0] += interval
        return CompletionState(now[0] >= duration, 'finished', {'step': 1})
    assert await_completion(DeferredToolResult('job-1', poll), clock=lambda: now[0],
                            notify=events.append) == 'finished'
    assert now[0] == duration
    assert events[0]['state'] == 'waiting' and events[-1]['state'] == 'finished'
    assert [e['state'] for e in events].count('progress') <= 1


def test_cancel_and_deadline_preserve_original_identity():
    now = [0.0]
    def poll(interval):
        now[0] += interval
        return CompletionState(False)
    job = DeferredToolResult('existing-job', poll)
    for cancelled, reason in [(False, 'deadline'), (True, 'cancelled')]:
        with pytest.raises(CompletionWaitError) as e:
            await_completion(job, timeout=2, clock=lambda: now[0], cancel_check=lambda: cancelled)
        assert e.value.result['task_id'] == 'existing-job'
        assert e.value.result['execution_status'] == 'unconfirmed'
        assert e.value.result['completion_wait'] == reason


def test_business_status_is_not_a_continuation():
    for result in [{'status': 'running', 'ticket': 'abcdef12'}, '{"status":"running"}',
                   {'success': False, 'error': 'job failed'}, {'images': [1], 'content': 'image'}]:
        assert await_completion(result) is result


def test_future_wait_and_failure_are_not_reexecuted():
    future = Future()
    timer = threading.Timer(0.02, lambda: future.set_result({'content': 'done', 'images': [1]}))
    timer.start()
    try:
        assert await_completion(future)['images'] == [1]
    finally:
        timer.join()
    broken = Future(); broken.set_exception(ValueError('job failed'))
    with pytest.raises(ValueError, match='job failed'):
        await_completion(broken)


@pytest.mark.parametrize('provider_name', ['openai', 'openrouter', 'deepseek', 'anthropic',
                                          'gemini', 'ollama', 'gemini_http', 'deepseek_http'])
def test_all_api_adapters_receive_only_final_result(provider_name, monkeypatch):
    from providers import get_provider
    import tool_completion
    monkeypatch.setattr(tool_completion, 'observe_wait', lambda event: None)
    p = get_provider(provider_name, api_key='test', model='test', system_prompt='test')
    submitted, polls, next_model = [], [], []
    def poll(interval):
        polls.append(1)
        return CompletionState(len(polls) == 2, '{"success":true,"answer":"done"}')
    def execute(*args):
        submitted.append(args)
        return DeferredToolResult('job', poll)
    def after(*args, **kwargs):
        assert len(polls) == 2
        assert '"answer": "done"' in json.dumps(args, default=str) or 'done' in str(args)
        next_model.append(1)
        yield {'type': 'final', 'content': 'done'}
    if provider_name in ('openai', 'openrouter', 'deepseek', 'ollama'):
        monkeypatch.setattr(p, '_agentic_loop', after)
        tc = {'call-1': {'id': 'call-1', 'name': 'probe', 'arguments': '{}'}}
        args = ([], '', '', tc, [], execute, 0) if provider_name != 'ollama' else ([], '', tc, [], execute, 0)
        assert list(p._execute_tools_and_continue(*args))[-1]['type'] == 'final'
    elif provider_name == 'anthropic':
        monkeypatch.setattr(p, '_agentic_loop', after)
        # Vendor's tool-result message and follow-up loop, not just the base helper.
        list(p._execute_tools_and_continue([], '', [{'id':'call-1', 'name':'probe', 'input':{}}], execute, 0))
    elif provider_name == 'gemini':
        fc = SimpleNamespace(name='probe', args={})
        result = p._execute_single_tool(fc, execute, 0)
        assert 'done' in result[0] and result[3] is False
        next_model.append(1)
    else:
        # REST adapters run the real process_message loop against two canned API turns.
        p._client = True
        calls = []
        if provider_name == 'deepseek_http':
            def request(*args, **kwargs):
                calls.append(1)
                if len(calls) == 1:
                    return {'choices':[{'message':{'tool_calls':[{'id':'call-1','type':'function','function':{'name':'probe','arguments':'{}'}}]}}]}
                assert len(polls) == 2
                next_model.append(1)
                return {'choices':[{'message':{'content':'done'}}]}
            monkeypatch.setattr(p, '_chat', request)
        else:
            def request(*args, **kwargs):
                calls.append(1)
                if len(calls) == 1:
                    return {'candidates':[{'content':{'parts':[{'functionCall':{'name':'probe','args':{}}}]}}]}
                assert len(polls) == 2
                next_model.append(1)
                return {'candidates':[{'content':{'parts':[{'text':'done'}]}}]}
            monkeypatch.setattr(p, '_generate', request)
        assert p.process_message('test', execute_tool=execute) == 'done'
    assert len(submitted) == 1 and len(next_model) == 1


def test_mcp_disconnect_recovers_original_failed_job(monkeypatch):
    import mcp_server
    calls=[]
    def post(path, payload, timeout):
        calls.append((path,payload))
        if path == '/ibl/execute': return json.dumps({'_transport_error':True})
        if len(calls)==2:return json.dumps({'transient':True,'status':'unreadable'})
        return json.dumps({'success':False,'error':'actual job error'})
    monkeypatch.setattr(mcp_server,'_post_backend',post)
    out=json.loads(asyncio.run(mcp_server.execute_ibl(code='[self:read]{path:"x"}')))
    assert out['error']=='actual job error'
    assert [p for p,_ in calls].count('/ibl/execute')==1
    assert len({p['ticket'] for _,p in calls})==1


@pytest.mark.parametrize('state', ['unknown','invalid'])
def test_mcp_missing_task_is_not_restarted(monkeypatch,state):
    import mcp_server
    calls=[]
    def post(path,payload,timeout):
        calls.append(path)
        return json.dumps({'_surface_timeout':True} if path=='/ibl/execute' else {'success':False,'status':state})
    monkeypatch.setattr(mcp_server,'_post_backend',post)
    out=json.loads(asyncio.run(mcp_server.execute_ibl(code='[self:read]{path:"x"}')))
    assert out['status']==state and out['ticket']
    assert calls==['/ibl/execute','/ibl/recover']


def test_cli_adapters_share_bridge_and_codex_bypasses_yielding_wrapper():
    from providers import get_provider
    from common.spill import SURFACE_CLIENT_WALL_S
    for name in ['codex','claude_code']:
        p=get_provider(name,api_key='',model='',system_prompt='')
        from providers.cli_provider import CliSubprocessProvider
        assert isinstance(p, CliSubprocessProvider)
    args=get_provider('codex',api_key='',model='',system_prompt='')._bridge_config_args('http')
    assert 'features.code_mode.direct_only_tool_namespaces=["mcp__indiebizos"]' in args

    assert f'mcp_servers.indiebizos.tool_timeout_sec={SURFACE_CLIENT_WALL_S}' in args


@pytest.mark.parametrize('name',['gemini_http','deepseek_http'])
def test_rest_cancel_does_not_start_next_model_call(name,monkeypatch):
    from providers import get_provider
    p=get_provider(name,api_key='test',model='test',system_prompt='')
    p._client=True
    monkeypatch.setattr(p,'_execute_with_retry',lambda *a,**k: pytest.fail('model invoked after cancellation'))
    assert '중단' in p.process_message('test',cancel_check=lambda:True)


def test_mcp_deadline_and_cancel_keep_ticket(monkeypatch):
    import mcp_server
    monkeypatch.setattr(mcp_server,'_post_backend',lambda *a:json.dumps({'_surface_timeout':True}))
    monkeypatch.setattr(mcp_server,'_MAX_WAIT_S',0)
    out=json.loads(mcp_server._execute_until_complete({'ticket':'abcdef12'},'abcdef12',lambda:False))
    assert out['completion_wait']=='deadline' and out['ticket']=='abcdef12'
    monkeypatch.setattr(mcp_server,'_MAX_WAIT_S',30)
    out=json.loads(mcp_server._execute_until_complete({'ticket':'abcdef12'},'abcdef12',lambda:True))
    assert out['completion_wait']=='cancelled' and out['execution_status']=='unconfirmed'


def test_callable_description_keeps_diagnostics_out_of_normal_model_context(monkeypatch,tmp_path):
    import model_result_view as view
    import ibl_v2_store
    from supervision_store import TurnStore
    guards=[{'message':'runtime check', 'call_path':['x'*1000]} for _ in range(62)]
    full={'callable_contract':{'name':'example','params':{},'result':'Record'},'status':'incomplete','guards':guards}
    monkeypatch.setattr(ibl_v2_store,'describe',lambda *a:full)
    monkeypatch.setattr(view,'evidence_store',lambda:TurnStore(tmp_path))
    out=view.describe_actions(['fn:example'],None,edition=2)
    definition=out['actions'][0]['definition']
    assert definition['runtime_checks']==62 and definition['status']=='incomplete'
    assert len(json.dumps(out))<2500
    args=definition['result_ref']['read_args'];args['path']=['guards',0]
    assert json.loads(view.read_result(args)['text'])==guards[0]


def test_actual_http_timeout_recovers_once_and_preserves_business_running(monkeypatch):
    """Real broken HTTP connection; job survives and is never resubmitted."""
    import time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import mcp_server
    state={'submits':0,'recovers':0,'done':False,'ticket':None}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path=='/ibl/execute':
                state['submits']+=1;state['ticket']=data['ticket']
                time.sleep(0.12);state['done']=True
            else:
                state['recovers']+=1
                assert data['ticket']==state['ticket']
                time.sleep(0.02)
            out=({'success':True,'status':'running','_recovered_from_ticket':state['ticket'],'answer':'terminal business value'}
                 if state['done'] else {'success':True,'status':'running'})
            body=json.dumps(out).encode()
            self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers()
            try:self.wfile.write(body)
            except (BrokenPipeError,ConnectionResetError):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    monkeypatch.setattr(mcp_server,'BASE',f'http://127.0.0.1:{server.server_port}')
    monkeypatch.setattr(mcp_server,'_RPC_WAIT_S',0.03)
    try:
        out=json.loads(asyncio.run(mcp_server.execute_ibl(code='probe')))
        assert out['answer']=='terminal business value' and out['status']=='running'
        assert state['submits']==1 and state['recovers']>=1
    finally:
        server.shutdown();server.server_close();thread.join()


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
