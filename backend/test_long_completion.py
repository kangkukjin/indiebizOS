"""Long programs, recovery, cancellation and CLI silence cross the same boundary."""
import boot_paths  # noqa: F401
import asyncio
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import pytest


@pytest.fixture
def channels(tmp_path, monkeypatch):
    import runtime_utils
    monkeypatch.setattr(runtime_utils, 'get_base_path', lambda: tmp_path)
    return tmp_path


def test_program_outlives_hour_and_explicit_budget_still_works():
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Budget, Runtime
    plan = compile_program('[def:f]($x){return $x+1}\n[1,2,3] >> [table:each]{parallel:2}{[fn:f]{x:$it}}')
    result = Runtime(plan, budget=Budget(started=time.monotonic()-7200)).run()
    assert result['success'] and result['value'] == [2,3,4]
    limited = Runtime(plan, budget=Budget(seconds=1, started=time.monotonic()-2)).run()
    assert not limited['success']
    from ibl_v2_entry import capabilities
    assert capabilities()['v2_budget']['seconds'] is None


@pytest.mark.parametrize('duration', [3600, 7200, 172800])
def test_completion_has_no_implicit_elapsed_wall(duration):
    from tool_completion import await_completion, DeferredToolResult, CompletionState
    now = [0]
    def poll(interval):
        now[0] += duration/2
        return CompletionState(now[0] >= duration, 'finished')
    assert await_completion(DeferredToolResult('job', poll), clock=lambda: now[0]) == 'finished'
    assert now[0] == duration


def test_mcp_recovers_for_over_hour_without_resubmit(monkeypatch):
    import mcp_server
    import tool_completion
    calls = []
    now = [0.0]
    real_wait = tool_completion.await_completion
    def wait(*a, **kw):
        return real_wait(*a, **kw, clock=lambda: now[0])
    monkeypatch.setattr(tool_completion, 'await_completion', wait)
    def post(path, payload, timeout):
        calls.append(path)
        now[0] += 1800
        if path == '/ibl/execute':
            return json.dumps({'_surface_timeout': True})
        return json.dumps({'status':'running'} if len(calls) < 4 else
                          {'success':True, 'value':'completed', '_recovered_from_ticket':'abcdef12'})
    monkeypatch.setattr(mcp_server, '_post_backend', post)
    out = json.loads(mcp_server._execute_until_complete({'ticket':'abcdef12'}, 'abcdef12', lambda: False))
    assert out['value'] == 'completed' and now[0] > 3600
    assert calls.count('/ibl/execute') == 1


def test_channel_does_not_mix_jobs_or_accept_paths(channels):
    import completion_lease as lease
    a, b = lease.create_channel(), lease.create_channel()
    lease.pulse(a, 'abcdef12')
    assert lease.is_waiting(a) and not lease.is_waiting(b)
    lease.pulse(a, 'abcdef34')
    lease.pulse(a, 'abcdef12', active=False)
    assert lease.is_waiting(a)  # parallel second tool is still waiting
    lease.pulse(a, 'abcdef34', active=False)
    assert not lease.is_waiting(a)
    lease.cancel_channel(a)
    assert lease.channel_cancelled(a) and not lease.channel_cancelled(b)
    lease.pulse('../outside', 'abcdef12')
    assert not lease.is_waiting('../outside')


def test_stale_lease_cannot_keep_cli_alive(channels, monkeypatch):
    import completion_lease as lease
    token = lease.create_channel()
    lease.pulse(token, 'abcdef12')
    monkeypatch.setattr(lease, 'LEASE_TTL_S', -1)
    assert not lease.is_waiting(token)
    monkeypatch.setattr(lease, 'LEASE_TTL_S', 45)
    path = lease._directory(token) / 'abcdef12.json'
    for data in ['[]', '{broken', '{"active":true,"at":"broken"}']:
        path.write_text(data)
        assert not lease.is_waiting(token)


def test_ticket_process_loss_and_gc(channels, monkeypatch):
    from common import spill
    monkeypatch.setattr(spill, '_root', lambda: str(channels / 'spill'))
    import completion_lease as lease
    ticket = 'abcdef12'
    spill.ticket_begin(ticket)
    path = Path(spill._ticket_path(ticket))
    os.utime(path, (time.time()-200000,)*2)
    spill.gc()
    assert path.exists(), 'active task must survive spill TTL'
    rec = json.loads(path.read_text())
    rec['owner']['born'] -= 1  # same pid reused by a different process
    path.write_text(json.dumps(rec))
    out = spill.ticket_recover(ticket)
    assert out['status'] == 'interrupted' and out['execution_status'] == 'unconfirmed'
    spill.ticket_finish(ticket, {'success':True, 'status':'running'})
    assert spill.ticket_wait(ticket, 10)['_recovered_from_ticket'] == ticket


def test_http_channel_and_stdio_identity_agree(channels, monkeypatch):
    import completion_lease as lease
    from providers import get_provider
    token = lease.create_channel()
    for name in ('codex', 'claude_code'):
        p = get_provider(name, api_key='', model='', system_prompt='')
        p._completion_channel = token
        if name == 'claude_code':
            monkeypatch.setenv('CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS', '120000')
            assert p._build_env()['CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS'] == '0'
        assert p._identity_env()['INDIEBIZOS_COMPLETION_CHANNEL'] == token
        headers = {k.lower():v for k,v in p._identity_headers().items()}
        ctx = SimpleNamespace(request_context=SimpleNamespace(request=SimpleNamespace(headers=headers)))
        assert lease.channel_from_context(ctx) == token
    monkeypatch.setenv('INDIEBIZOS_COMPLETION_CHANNEL', token)
    assert lease.channel_from_context(None) == token


def test_api_carries_cooperative_cancellation(channels, monkeypatch):
    import completion_lease as lease
    import system_tools
    from api_ibl import execute_ibl_code, IBLRequest
    token = lease.create_channel()
    calls = []
    def execute(*args, cancel_check=None, **kwargs):
        calls.append(1)
        assert cancel_check and not cancel_check()
        lease.cancel_channel(token)
        assert cancel_check()
        return {'success':False, 'error':'cancelled'}
    monkeypatch.setattr(system_tools, '_execute_ibl_unified', execute)
    out = asyncio.run(execute_ibl_code(IBLRequest(code='return 1', completion_channel=token)))
    assert not out['success'] and calls == [1]


def _child(pulses=True):
    root = str(Path(__file__).resolve().parent)
    return f'''
import sys, os, time, json
sys.path.insert(0, {root!r})
import boot_paths
from completion_lease import pulse
channel = os.environ['INDIEBIZOS_COMPLETION_CHANNEL']
for i in range(35):
    if {pulses!r} or i == 0: pulse(channel, 'abcdef12')
    time.sleep(.1)
pulse(channel, 'abcdef12', active=False)
print(json.dumps({{'type':'text','content':'finished'}}), flush=True)
'''


def test_real_cli_silent_tool_outlives_idle_wall():
    from test_cli_stream_deadline import _make, _FakeCli
    class Waiting(_FakeCli):
        CHILD_CODE = _child()
    p = _make(Waiting)
    started = time.monotonic()
    events = list(p.process_message_stream('test'))
    assert time.monotonic() - started > p.STREAM_IDLE_TIMEOUT_SEC * 3
    assert not any(e['type']=='error' for e in events), events
    assert any('finished' in e.get('content','') for e in events)


def test_cli_cancel_works_while_stdout_is_silent():
    from test_cli_stream_deadline import _make, _FakeCli
    class Waiting(_FakeCli):
        CHILD_CODE = _child()
    p = _make(Waiting)
    started = time.monotonic()
    events = list(p.process_message_stream('test', cancel_check=lambda: time.monotonic()-started > .6))
    assert time.monotonic()-started < 3
    assert any(e['type']=='error' and '취소' in e.get('content','') for e in events)


def test_cli_dead_waiter_lease_expires(monkeypatch):
    import completion_lease
    from test_cli_stream_deadline import _make, _FakeCli
    monkeypatch.setattr(completion_lease, 'LEASE_TTL_S', .2)
    class Silent(_FakeCli):
        CHILD_CODE = _child(False)
    p = _make(Silent)
    events = list(p.process_message_stream('test'))
    assert any('무응답 마감' in e.get('content','') and 'abcdef12' in e['content'] for e in events)


def test_stdio_config_carries_identity_even_when_cli_filters_env(channels, monkeypatch, tmp_path):
    import completion_lease as lease
    from providers import get_provider, claude_code, codex
    import tomllib
    token = lease.create_channel()
    p = get_provider('codex', api_key='', model='', system_prompt='')
    p._completion_channel = token
    monkeypatch.setattr(codex, '_stdio_bridge_command', lambda: [sys.executable, 'mcp_server.py'])
    args = p._bridge_config_args('stdio')
    env = next(a for a in args if a.startswith('mcp_servers.indiebizos.env='))
    assert tomllib.loads(env)['mcp_servers']['indiebizos']['env']['INDIEBIZOS_COMPLETION_CHANNEL'] == token
    p = get_provider('claude_code', api_key='', model='', system_prompt='')
    p._completion_channel = token
    cfg = tmp_path / 'config.json'
    original = {'mcpServers': {'indiebizos': {'command': sys.executable, 'env': {'custom':'kept'}}}}
    cfg.write_text(json.dumps(original))
    monkeypatch.setattr(claude_code, 'get_mcp_config_path', lambda: str(cfg))
    monkeypatch.setenv('INDIEBIZOS_MCP_HTTP', '0')
    handle = p._mcp_bridge_acquire()
    try:
        env = json.loads(Path(handle).read_text())['mcpServers']['indiebizos']['env']
        assert env['INDIEBIZOS_COMPLETION_CHANNEL'] == token and env['custom'] == 'kept'
        assert json.loads(cfg.read_text()) == original
    finally:
        p._mcp_bridge_release(handle)
    assert not Path(handle).exists()


def test_generated_old_timeout_migrates_but_custom_timeout_survives(tmp_path):
    from providers.cli_provider import _ensure_tool_timeout
    from completion_lease import MCP_CLIENT_TIMEOUT_S
    cfg = tmp_path / 'config.json'
    for old, expected in [(900000, MCP_CLIENT_TIMEOUT_S*1000), (123456, 123456)]:
        cfg.write_text(json.dumps({'mcpServers':{'indiebizos':{'command':'python','timeout':old}}}))
        _ensure_tool_timeout(cfg)
        assert json.loads(cfg.read_text())['mcpServers']['indiebizos']['timeout'] == expected


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
