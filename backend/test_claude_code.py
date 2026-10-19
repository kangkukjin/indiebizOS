"""Claude CLI roles expose only the command bridge the execution role can use."""
import boot_paths  # noqa: F401
import pytest
from providers.claude_code import ClaudeCodeProvider

COMMAND = 'mcp__indiebizos__run_command'


@pytest.mark.parametrize('no_tools', [False, True])
def test_image_instruction_matches_execution_and_oneshot_tools(no_tools):
    provider = ClaudeCodeProvider(api_key='', model='test', system_prompt='test')
    provider.no_tools = no_tools
    prompt = provider._image_prompt_prefix(['/tmp/photo.jpg'])
    assert '/tmp/photo.jpg' in prompt
    assert ('Read 도구' in prompt) == no_tools
    assert ('[engines:image_read]' in prompt) != no_tools


@pytest.mark.parametrize('repair', [False, True])
@pytest.mark.parametrize('mode', ['supervisor', 'response', 'library', 'normal'])
def test_repair_command_is_not_exposed_to_other_roles(monkeypatch, repair, mode):
    monkeypatch.setattr('repair_context.active', lambda: repair)
    monkeypatch.setattr('research_context.library_only', lambda: mode == 'library')
    provider = ClaudeCodeProvider(api_key='', model='test', system_prompt='test')
    provider._binary_path = 'claude'
    provider.agent_role = 'consciousness' if mode == 'supervisor' else 'execution'
    provider.restricted_response_repair = mode == 'response'
    cmd = provider._build_command(mcp_config_path='/tmp/example.json')
    allowed = cmd[cmd.index('--allowed-tools') + 1].split(',')
    denied = cmd[cmd.index('--disallowed-tools') + 1].split(',')
    if repair and mode == 'normal':
        assert COMMAND in allowed and COMMAND not in denied
    else:
        assert COMMAND not in allowed and COMMAND in denied
    if mode in {'supervisor', 'response'}:
        assert 'mcp__indiebizos__execute_ibl' not in allowed


@pytest.mark.parametrize('stream', [False, True])
@pytest.mark.parametrize('tools_mode', [None, 'none', 'read'])
@pytest.mark.parametrize('disabled', [False, True])
def test_session_persistence_controls_disk_and_resume(stream, tools_mode, disabled):
    provider = ClaudeCodeProvider(api_key='', model='test', system_prompt='test')
    provider._binary_path = 'claude'
    provider.disable_session_persistence = disabled
    cmd = provider._build_command(
        stream=stream, tools_mode=tools_mode, resume_session_id='prior-session')
    assert ('--no-session-persistence' in cmd) == disabled
    assert ('--resume' in cmd) != disabled
    assert ('prior-session' in cmd) != disabled


def test_oneshot_passes_disk_persistence_policy_to_claude(monkeypatch):
    from consciousness_agent import call_oneshot_provider

    commands = []

    def process(provider, **kwargs):
        commands.append(provider._build_command(tools_mode='none'))
        return '{}'

    monkeypatch.setattr(ClaudeCodeProvider, 'process_message', process)
    provider = ClaudeCodeProvider(api_key='', model='test', system_prompt='test')
    provider._binary_path = 'claude'
    assert call_oneshot_provider(provider, 'test') == '{}'
    assert '--no-session-persistence' in commands[0]
    assert provider.disable_session_persistence is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
