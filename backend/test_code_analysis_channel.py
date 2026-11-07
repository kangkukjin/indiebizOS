import boot_paths  # noqa: F401
import json
import shlex
import sys
from pathlib import Path

import pytest
from code_analysis_channel import request
from code_analysis_bridge import Bridge
from coding_store import CodingStore
from coding_process import available


@pytest.mark.skipif(not available(), reason='macOS process isolation')
def test_scoped_cli_in_sandbox_nested_ipc_and_readonly_ibl(tmp_path):
    root = tmp_path / 'source'; root.mkdir(); (root / 'a.py').write_text('answer = 42\n')
    outside = tmp_path / 'outside.py'; outside.write_text('safe')
    bridge = Bridge(root, tmp_path / 'runtime', lambda: False, CodingStore(tmp_path / 'state'))
    try:
        with pytest.raises(RuntimeError, match='격리된'):
            request(bridge.channel.config, {'op': 'ibl', 'args': {'code': '[self:write]{path:"x",content:"x"}'}})
        code = json.dumps({'op': 'read', 'selector': {'analysis': 'hover', 'path': 'a.py', 'line': 1, 'column': 2}})
        cli = Path(__file__).parent / 'code_analysis_cli.py'
        command = 'printf %s ' + shlex.quote(code) + ' | ' + shlex.quote(sys.executable) + ' ' + shlex.quote(str(cli))
        output = request(bridge.channel.config, {'op': 'command', 'command': command})
        assert output['success'], output
        assert 'Literal[42]' in output['output']
        output = request(bridge.channel.config, {'op': 'command', 'command': 'echo changed > ' + shlex.quote(str(outside))})
        assert not output['success'] and outside.read_text() == 'safe'
    finally:
        bridge.close()
    assert not bridge.channel.config.exists()


@pytest.mark.skipif(not available(), reason='macOS process isolation')
def test_ibl_cli_and_stdio_mcp_share_one_provider_neutral_session(tmp_path, monkeypatch):
    import subprocess
    root = tmp_path / 'source'; root.mkdir(); (root / 'a.py').write_text('answer = 42\n')
    store = CodingStore(tmp_path / 'state')
    bridge = Bridge(root, tmp_path / 'runtime', lambda: False, store)
    monkeypatch.setattr('coding_projects.CodingStore', lambda: store)
    code = '[self:workspace]{op:"read",kind:"code",selector:{analysis:"hover",path:"a.py",line:1,column:2}}'
    try:
        direct = request(bridge.channel.config, {'op': 'read', 'selector': {'analysis': 'hover', 'path': 'a.py', 'line': 1, 'column': 2}})
        through_ibl = request(bridge.channel.config, {'op': 'ibl', 'args': {'code': code}})
        assert direct['analysis']['generation'] in str(through_ibl), through_ibl
        cli = Path(__file__).parent / 'code_analysis_cli.py'
        messages = [
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2024-11-05'}},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
            {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': 'execute_ibl', 'arguments': {'code': code}}},
        ]
        proc = subprocess.run([sys.executable, str(cli), '--mcp', '--connection', str(bridge.channel.config)],
                              input='\n'.join(json.dumps(m) for m in messages) + '\n', text=True, capture_output=True, timeout=45)
        assert proc.returncode == 0, proc.stderr
        output = [json.loads(line) for line in proc.stdout.splitlines()]
        assert {t['name'] for t in output[1]['result']['tools']} == {'execute_ibl', 'run_command'}
        assert direct['analysis']['generation'] in str(output[2]), output[2]
    finally:
        bridge.close()


@pytest.mark.skipif(not available(), reason='macOS process isolation')
def test_command_response_includes_diagnostics_without_explicit_lsp_call(tmp_path):
    root = tmp_path / 'source'; root.mkdir()
    bridge = Bridge(root, tmp_path / 'runtime', lambda: False, CodingStore(tmp_path / 'state'))
    try:
        result = request(bridge.channel.config, {'op': 'command',
            'command': "printf 'answer: int = \"bad\"\\n' > a.py"})
        assert result['success'] and result['exit_code'] == 0
        assert result['code_diagnostics'][0]['items'], result
        assert result['code_diagnostics'][0]['automatic'] is True
    finally:
        bridge.close()
