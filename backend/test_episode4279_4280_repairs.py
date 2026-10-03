"""CLI 승인/전송 경계와 검색 행 단위의 실제 실패를 재현한다."""
import asyncio
import json
import time

import pytest
import boot_paths  # noqa: F401
from test_conscious_supervisor import supervisor  # noqa: F401
from test_grep_counts import GREP
from providers.codex import CodexProvider


@pytest.mark.parametrize('transport', ['http', 'stdio'])
@pytest.mark.parametrize('resume', [None, 'previous-session'])
def test_repair_cli_allows_only_guarded_bridge_and_keeps_native_readonly(monkeypatch, transport, resume):
    monkeypatch.setattr('repair_context.active', lambda: True)
    monkeypatch.setattr('providers.codex._stdio_bridge_command', lambda: ['python', 'mcp_server.py'])
    provider = CodexProvider(api_key='', model='test', system_prompt='test')
    provider._binary_path = 'codex'
    cmd = provider._build_command(mcp_config_path=transport, resume_session_id=resume)
    assert '--dangerously-bypass-approvals-and-sandbox' not in cmd
    assert cmd[cmd.index('--sandbox') + 1] == 'read-only'
    assert 'approval_policy="never"' in cmd
    assert 'mcp_servers.indiebizos.enabled_tools=["execute_ibl","read_guide","run_command"]' in cmd
    for name in ['execute_ibl', 'read_guide', 'run_command']:
        assert f'mcp_servers.indiebizos.tools.{name}.approval_mode="approve"' in cmd
    assert 'mcp__indiebizos__run_command' in provider._build_prompt_with_history('repair', [])
    monkeypatch.setattr('repair_context.active', lambda: False)
    normal = provider._build_command(mcp_config_path=transport)
    assert not any('.tools.execute_ibl.approval_mode=' in arg for arg in normal)
    assert 'mcp_servers.indiebizos.disabled_tools=["run_command"]' in normal


def test_client_mcp_rejection_retains_reason_and_is_counted_once(supervisor):
    provider = CodexProvider(api_key='', model='test', system_prompt='test')
    reason = 'MCP tool call requires approval, but approval policy is never'
    item = {'id': 'rejected', 'type': 'mcp_tool_call', 'server': 'indiebizos',
            'tool': 'execute_ibl', 'arguments': {'code': 'return 1'},
            'status': 'failed', 'error': {'message': reason}}
    events = [e for e, _ in provider._translate_stream_event(
        {'type': 'item.completed', 'item': item}, '', time.time())]
    assert [e['type'] for e in events] == ['tool_start', 'tool_result']
    assert reason in events[-1]['result']
    assert events[-1]['is_error'] and events[-1]['transport_error']
    for e in events:
        supervisor.observe_native(e)
    assert supervisor.store.cost['execution_calls'] == 1
    assert supervisor.store.cost['execution_failures'] == 1
    assert reason in supervisor.store.read_evidence(supervisor.store.tool_index()[0]['result']['id'])['text']
    # 서버에 도달한 업무 실패는 서버가 이미 기록하며 CLI가 재집계하지 않는다.
    supervisor.run_tool('execute_ibl', {'code': 'bad'}, lambda: '{"success":false,"error":"bad"}')
    supervisor.observe_native({'type': 'tool_start', 'id': 'server', 'name': 'mcp__indiebizos__execute_ibl', 'input': {}})
    supervisor.observe_native({'type': 'tool_result', 'id': 'server', 'name': 'mcp__indiebizos__execute_ibl',
                               'is_error': True, 'result': '{"success":false}', 'transport_error': False})
    assert supervisor.store.cost['execution_calls'] == 2
    assert supervisor.store.cost['execution_failures'] == 2
    assert not supervisor._bridge_pending


@pytest.mark.parametrize('use_rg', [True, False])
@pytest.mark.parametrize('mode', ['count', 'files_with_matches'])
def test_grep_summary_units_and_no_unnecessary_content_scan(tmp_path, monkeypatch, use_rg, mode):
    if use_rg and not GREP._RG_BIN:
        pytest.skip('ripgrep unavailable')
    if not use_rg:
        monkeypatch.setattr(GREP, '_RG_BIN', None)
    else:
        monkeypatch.setattr(GREP, '_rg_grep', lambda *a: pytest.fail('summary must not read match bodies'))
    (tmp_path / 'a.txt').write_text('needle\nneedle ' + 'x' * 800 + '\n')
    (tmp_path / 'b.txt').write_text('needle\n')
    result = json.loads(GREP.run({'path': str(tmp_path), 'pattern': 'needle', 'output_mode': mode}, str(tmp_path)))
    assert result['total'] == result['total_files'] == len(result['items']) == 2
    assert result['total_matches'] == 3
    assert result['total_complete'] is True
    assert result['truncated'] is False
    assert result['truncations'] == []
    if mode == 'count':
        assert sum(item['매칭 수'] for item in result['items']) == 3


def test_grep_incomplete_fallback_never_claims_complete_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(GREP, '_RG_BIN', None)
    (tmp_path / 'a.txt').write_text('needle\n' * 5)
    result = json.loads(GREP.run({'path': str(tmp_path), 'pattern': 'needle',
                                 'output_mode': 'count', 'limit': 1}, str(tmp_path)))
    assert result['total_complete'] is False
    assert result['truncated'] is True
    assert result['truncations'][0]['scope'] == 'source'


def test_repair_command_requires_owner_and_grant_and_preserves_context(supervisor, monkeypatch):
    import api_supervision
    import thread_context as tc
    calls = []
    def execute(name, payload, path, **kw):
        calls.append((name, payload, path, tc.get_current_agent_id(), tc.get_current_task_id()))
        return '{"success":true,"verification":{"status":"passed"}}'
    monkeypatch.setattr('system_tools.execute_tool', execute)
    monkeypatch.setattr('repair_context.active', lambda: False)
    assert not api_supervision.dispatch('worker', supervisor.task, {'command': 'test'}, repair_command=True)['success']
    monkeypatch.setattr('repair_context.active', lambda: True)
    assert not api_supervision.dispatch(supervisor.supervisor_id, supervisor.task, {'command': 'test'}, repair_command=True)['success']
    assert not api_supervision.dispatch('unknown', supervisor.task, {'command': 'test'}, repair_command=True)['success']
    assert not calls
    before = tc.snapshot()
    result = api_supervision.dispatch('worker', supervisor.task, {'command': 'test'}, repair_command=True)
    assert result['success']
    assert calls == [('run_command', {'command': 'test'}, supervisor.project_path, 'worker', supervisor.task)]
    assert supervisor.store.cost['execution_calls'] == 1
    assert tc.snapshot() == before


def test_mcp_repair_command_carries_identity_and_failure(monkeypatch):
    import mcp_server as m
    seen = []
    monkeypatch.setattr(m, '_http_identity', lambda ctx: ('worker', '/untrusted', 'repair-task', ''))
    def post(path, payload, timeout):
        seen.append((path, payload, timeout))
        return '{"success":false,"error":"no repair grant"}'
    monkeypatch.setattr(m, '_post_backend', post)
    result = asyncio.run(m.run_command('node --test tests.mjs', timeout=120))
    assert result.isError
    assert 'no repair grant' in result.content[0].text
    assert seen == [('/ibl/repair/command', {'agent_id': 'worker', 'task_id': 'repair-task',
                    'payload': {'command': 'node --test tests.mjs', 'timeout': 120, 'approved': False}}, 130)]


def test_claude_repair_exposes_guarded_command_without_native_shell(monkeypatch):
    from providers.claude_code import ClaudeCodeProvider
    monkeypatch.setattr('repair_context.active', lambda: True)
    p = ClaudeCodeProvider(api_key='', model='test', system_prompt='test')
    p._binary_path = 'claude'
    cmd = p._build_command(mcp_config_path='/tmp/test.json')
    assert cmd[cmd.index('--tools') + 1] == ''
    allowed = cmd[cmd.index('--allowed-tools') + 1].split(',')
    assert 'mcp__indiebizos__run_command' in allowed
    assert 'Bash' not in allowed


def test_repair_command_route_reaches_same_workspace_and_records_real_check(tmp_path, supervisor, monkeypatch):
    import api_supervision
    import subprocess
    import sys
    import shlex
    import system_tools
    from test_repair_staging import _load_handler
    root = tmp_path / 'isolated-repo'
    root.mkdir()
    for args in [['init', '-q'], ['config', 'user.email', 'test@example.test'], ['config', 'user.name', 'Test']]:
        subprocess.run(['git', *args], cwd=root, check=True)
    (root / '.gitignore').write_text('.worktrees/\ndata/system_ai_state/\n')
    (root / 'a.txt').write_text('live')
    subprocess.run(['git', 'add', '.'], cwd=root, check=True)
    subprocess.run(['git', 'commit', '-qm', 'fixture'], cwd=root, check=True)
    h = _load_handler()
    monkeypatch.setattr(h, '_REPO_ROOT', root)
    monkeypatch.setattr(h, '_red_grant_active', lambda: True)
    monkeypatch.setattr(h, '_staging_key', lambda: supervisor.task)
    monkeypatch.setattr('repair_context.active', lambda: True)
    st = h._staging_mod()
    monkeypatch.setattr(st, '_repair_owner', lambda: 'worker')
    monkeypatch.setattr(system_tools, 'load_tool_handler', lambda name: h)
    session = st.ensure_session(str(root), supervisor.task)
    wt = root / session['worktree']
    (wt / 'a.txt').write_text('candidate')
    code = 'from pathlib import Path; assert Path("a.txt").read_text()=="candidate"; print("1 passed")'
    command = shlex.join([sys.executable, '-c', code])
    result = api_supervision.dispatch('worker', supervisor.task, {'command': command}, repair_command=True)
    assert result.get('success'), result
    assert result['verification']['status'] == 'passed', result
    stored = st.load_session(str(root), supervisor.task)
    assert stored['execution_checks'][-1]['id'] == result['verification']['id']
    assert stored['execution_checks'][-1]['evidence_ref']['id']
    assert (root / 'a.txt').read_text() == 'live'
    assert supervisor.store.cost['execution_calls'] == 1


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
