"""중앙 CLI 기어의 도구·신원 경계를 실제 loopback MCP로 검사한다."""
import boot_paths  # noqa: F401
import json
import threading
from types import SimpleNamespace
import urllib.request

import pytest
import principal
import member_runtime
from member_cli import MemberToolBridge, MemberClaudeProvider


def test_loopback_only_exposes_member_tools_and_restores_principal(tmp_path):
    seen = []
    def execute(name, args, *rest):
        seen.append((principal.current().key(), member_runtime.current()['task_id'], name, args))
        return json.dumps({'success': True})
    provider = MemberClaudeProvider(api_key='', model='opus', system_prompt='', tools=[
        {'name': 'execute_ibl', 'input_schema': {'type': 'object'}}])
    with principal.narrow(principal.member('a', 4, 'd')), member_runtime.turn_scope(tmp_path, 'd', 'task', threading.Event(), {}):
        bridge = MemberToolBridge(provider, execute, None)
    config = bridge.config()['mcpServers']['member']
    def rpc(method, params=None, authenticated=True):
        headers = {'Content-Type': 'application/json'}
        if authenticated:
            headers.update(config['headers'])
        request = urllib.request.Request(config['url'], json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}}).encode(), headers)
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.load(response)['result']
    try:
        with pytest.raises(urllib.error.HTTPError) as error:
            rpc('tools/list', authenticated=False)
        assert error.value.code == 403
        assert [t['name'] for t in rpc('tools/list')['tools']] == ['execute_ibl']
        assert rpc('tools/call', {'name': 'Bash', 'arguments': {'command': 'pwd'}})['isError']
        rpc('tools/call', {'name': 'execute_ibl', 'arguments': {'code': 'test'}})
        assert seen == [('member:a', 'task', 'execute_ibl', {'code': 'test'})]
        bridge.closed = True
        assert rpc('tools/call', {'name': 'execute_ibl'})['isError']
        assert len(seen) == 1
    finally:
        bridge.close()


def test_member_cli_has_no_native_tools_owner_config_or_persistence(tmp_path, monkeypatch):
    from providers import get_provider
    monkeypatch.setenv('INDIEBIZ_API_KEY', 'owner-canary')
    with principal.narrow(principal.member('a', 4, 'd')):
        provider = get_provider('claude_code', api_key='', model='opus', system_prompt='member prompt')
        assert isinstance(provider, MemberClaudeProvider)
        with pytest.raises(PermissionError):
            get_provider('codex', api_key='', model='x', system_prompt='')
    provider._binary_path = '/test/claude'
    provider._member_bridge = SimpleNamespace(tools={'execute_ibl': {}})
    provider._member_root = tmp_path
    provider._effective_token = 'sk-ant-oat-test'
    command = provider._build_command('/private/mcp.json', stream=True)
    assert command[command.index('--tools') + 1] == ''
    assert command[command.index('--setting-sources') + 1] == ''
    assert '--strict-mcp-config' in command and '--no-session-persistence' in command
    assert command[command.index('--allowed-tools') + 1] == 'mcp__member__execute_ibl'
    prompt_path = provider._write_system_prompt_file()
    command = provider._build_command('/private/mcp.json', stream=True, system_prompt_file=prompt_path)
    assert '--system-prompt-file' in command and 'member prompt' not in command
    assert (tmp_path / 'system-prompt.txt').read_text() == 'member prompt'
    env = provider._build_env()
    assert 'INDIEBIZ_API_KEY' not in env
    assert env['CLAUDE_CONFIG_DIR'] == str(tmp_path / 'config')
    assert env['CLAUDE_CODE_OAUTH_TOKEN'] == 'sk-ant-oat-test'


def test_central_execution_gear_is_not_downgraded(monkeypatch):
    import model_resolver
    from member_runner import MemberRunner
    monkeypatch.setattr(model_resolver, 'resolve', lambda role, **kwargs: {
        'provider': 'claude_code', 'model': 'opus', 'api_key': '', 'source': 'gear:최대'})
    runner = MemberRunner.__new__(MemberRunner)
    runner.config = {}
    config = runner._resolve_execution_config({}, None)
    assert (config['provider'], config['model']) == ('claude_code', 'opus')


def test_member_oneshot_never_reuses_or_populates_owner_cache(monkeypatch, tmp_path):
    import model_resolver as resolver
    from consciousness_agent import call_oneshot_provider
    descriptor = {'provider': 'claude_code', 'model': 'opus', 'api_key': ''}
    monkeypatch.setattr(MemberClaudeProvider, 'init_client', lambda self: setattr(self, '_client', True))
    # 실제 외부 호출 없이 원샷의 회원 허용과 모델 선택을 검사한다.
    monkeypatch.setattr(MemberClaudeProvider, 'process_message', lambda self, **kwargs: self.model)
    monkeypatch.setattr(resolver, '_provider_cache', {})
    owner = resolver._provider_from_desc(descriptor, oneshot=True)
    owner_cache = dict(resolver._provider_cache)
    with principal.narrow(principal.member('a', 4, 'd')), member_runtime.turn_scope(tmp_path, 'd', 'task', threading.Event(), {}):
        member = resolver._provider_from_desc(descriptor, oneshot=True)
        assert member is not owner and isinstance(member, MemberClaudeProvider)
        assert call_oneshot_provider(member, 'test', role='evaluate') == 'opus'
        with pytest.raises(PermissionError):
            call_oneshot_provider(owner, 'test', role='evaluate')
    assert resolver._provider_cache == owner_cache


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
