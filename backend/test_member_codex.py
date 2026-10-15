"""회원 Codex의 실제 도구 노출·MCP 왕복·usage 및 개인 설정 격리."""
import boot_paths  # noqa: F401
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import principal
import member_runtime
import member_codex as M
from providers.codex import find_codex_binary


@pytest.fixture
def owner_home(tmp_path, monkeypatch):
    home = tmp_path / 'owner'
    home.mkdir()
    model = {
        'slug': 'fixture-model', 'display_name': 'Fixture', 'description': '',
        'supported_reasoning_levels': [{'effort': 'low', 'description': 'Low'}],
        'default_reasoning_level': 'low', 'shell_type': 'unified_exec',
        'visibility': 'list', 'supported_in_api': True, 'priority': 0,
        'support_verbosity': False, 'truncation_policy': {'mode': 'tokens', 'limit': 10000},
        'apply_patch_tool_type': 'freeform', 'tool_mode': 'code_mode_only',
        'multi_agent_version': 'v2', 'experimental_supported_tools': ['clock'],
        'use_responses_lite': True, 'context_window': 128000,
    }
    (home / 'models_cache.json').write_text(json.dumps({'models': [model]}))
    (home / 'config.toml').write_text('developer_instructions="OWNER_CONFIG_CANARY"')
    monkeypatch.setattr(M, '_codex_home', lambda: home)
    return home


def test_catalog_missing_model_fails_closed(owner_home, tmp_path):
    provider = M.MemberCodexProvider(api_key='', model='missing-model', system_prompt='')
    provider._member_root = tmp_path
    with pytest.raises(RuntimeError, match='모델 목록'):
        provider._write_model_catalog()


def test_env_only_auth_is_shared(owner_home, tmp_path, monkeypatch):
    from types import SimpleNamespace
    (owner_home / 'auth.json').write_text('{"fixture":true}')
    monkeypatch.setenv('INDIEBIZ_API_KEY', 'owner-canary')
    monkeypatch.setenv('CODEX_HOME', str(owner_home))
    monkeypatch.setenv('OPENAI_API_KEY', 'environment-key-must-not-change-billing')
    provider = M.MemberCodexProvider(api_key='', model='fixture-model', system_prompt='')
    provider._effective_key = None
    provider._member_root = tmp_path / 'turn'
    provider._member_bridge = SimpleNamespace(secret='turn-only-token')
    env = provider._build_env()
    assert 'INDIEBIZ_API_KEY' not in env and 'OPENAI_API_KEY' not in env
    assert env['INDIEBIZ_MEMBER_MCP_TOKEN'] == 'turn-only-token'
    home = Path(env['CODEX_HOME'])
    assert home != owner_home
    assert (home / 'auth.json').resolve() == owner_home / 'auth.json'
    assert not (home / 'config.toml').exists()
    assert not (home / 'models_cache.json').exists()


def _tool_names(value):
    if isinstance(value, list):
        return set().union(*(_tool_names(v) for v in value)) if value else set()
    if not isinstance(value, dict):
        return set()
    if value.get('type') in ('function', 'custom'):
        return {value['name']}
    return set().union(*(_tool_names(v) for v in value.values())) if value else set()


@pytest.mark.system
@pytest.mark.parametrize('no_tools', [False, True])
def test_installed_codex_exposes_only_member_tools_and_round_trips(owner_home, tmp_path, monkeypatch, no_tools):
    """모델만 로컬 SSE로 대체. 설치 CLI의 실제 tool 목록·dispatch·번역기를 검사한다."""
    binary = find_codex_binary()
    if not binary:
        pytest.skip('Codex CLI not installed')
    requests, calls = [], []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append(request)
            n = len(requests)
            if n == 1 and not no_tools:
                item = {'id': 'fc_forbidden', 'type': 'function_call', 'call_id': 'call_forbidden',
                        'namespace': 'functions', 'name': 'exec_command',
                        'arguments': json.dumps({'cmd': f'touch {tmp_path / "central-write"}'}),
                        'status': 'completed'}
            elif n == 2 and not no_tools:
                item = {'id': 'fc_member', 'type': 'function_call', 'call_id': 'call_member',
                        'namespace': 'mcp__member', 'name': 'run_command', 'arguments': '{"command":"member-test"}',
                        'status': 'completed'}
            else:
                item = {'id': 'msg_final', 'type': 'message', 'role': 'assistant', 'status': 'completed',
                        'content': [{'type': 'output_text', 'text': 'MEMBER_OK', 'annotations': []}]}
            response = {'id': f'resp_{n}', 'object': 'response', 'status': 'completed', 'output': [item],
                        'usage': {'input_tokens': 100, 'output_tokens': 5, 'total_tokens': 105}}
            events = [
                {'type': 'response.created', 'response': {**response, 'status': 'in_progress', 'output': []}},
                {'type': 'response.output_item.added', 'output_index': 0, 'item': item},
                {'type': 'response.output_item.done', 'output_index': 0, 'item': item},
                {'type': 'response.completed', 'response': response},
            ]
            body = ''.join('event: ' + e['type'] + '\ndata: ' + json.dumps(e) + '\n\n' for e in events).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    provider = M.MemberCodexProvider(api_key='', model='fixture-model:low', system_prompt='MEMBER_PROMPT', tools=[
        {'name': 'run_command', 'description': '회원 PC에서 실행', 'input_schema': {
            'type': 'object', 'properties': {'command': {'type': 'string'}}, 'required': ['command']}}])
    provider._binary_path = binary
    provider._effective_key = None
    provider._client = {'binary': binary}
    provider.no_tools = no_tools
    build = provider._build_command

    def command(**kwargs):
        args = build(**kwargs)
        args[-1:-1] = ['-c', 'model_provider="fixture"', '-c',
                       f'model_providers.fixture={{name="fixture",base_url="http://127.0.0.1:{server.server_port}/v1",'
                       'wire_api="responses",requires_openai_auth=false}']
        return args

    monkeypatch.setattr(provider, '_build_command', command)

    def execute(name, args, *rest):
        calls.append((principal.current().key(), member_runtime.current()['task_id'], name, args))
        return 'RESULT_FROM_MEMBER_PC'

    try:
        with principal.narrow(principal.member('fixture', 1, 'pc')), member_runtime.turn_scope(
                tmp_path / 'state', 'pc', 'task', threading.Event(), {}):
            result = provider.process_message('회원 PC에서 실행하세요.', execute_tool=execute)
        assert result == 'MEMBER_OK'
        assert calls == ([] if no_tools else [('member:fixture', 'task', 'run_command', {'command': 'member-test'})])
        assert len(requests) == (1 if no_tools else 3)
        assert _tool_names(requests[0]) == (set() if no_tools else {
            'run_command', 'list_mcp_resources', 'list_mcp_resource_templates', 'read_mcp_resource'})
        assert 'OWNER_CONFIG_CANARY' not in json.dumps(requests)
        if not no_tools:
            assert 'unsupported call' in json.dumps(requests[1])
            assert 'RESULT_FROM_MEMBER_PC' in json.dumps(requests[-1])
        assert not (tmp_path / 'central-write').exists()
        assert provider.metrics.total_input_tokens == 100 * len(requests)
        assert provider.metrics.total_output_tokens == 5 * len(requests)
        assert not provider._member_root.exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
