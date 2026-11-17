"""Claude CLI roles expose only the command bridge the execution role can use."""
import boot_paths  # noqa: F401
import pytest
from providers.claude_code import ClaudeCodeProvider

COMMAND = 'mcp__indiebizos__run_command'


@pytest.mark.parametrize('role', ['execution', 'consciousness', 'response'])
def test_todo_bridge_is_exposed_only_to_execution(role):
    provider = ClaudeCodeProvider(api_key='', model='test', system_prompt='test')
    provider._binary_path = 'claude'
    provider.agent_role = role
    provider.restricted_response_repair = role == 'response'
    cmd = provider._build_command(mcp_config_path='/tmp/example.json')
    name = 'mcp__indiebizos__todo_write'
    allowed = cmd[cmd.index('--allowed-tools') + 1].split(',')
    denied = cmd[cmd.index('--disallowed-tools') + 1].split(',')
    assert (name in allowed) == (role == 'execution')
    assert (name in denied) == (role != 'execution')
    assert 'TodoWrite' not in provider.EAGER_BUILTIN_TOOLS


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


# ── L84-3 (2026-10-20): 발화 언어 → CLI `language` 스위치 (docs/ANSWER_LANGUAGE_TRACE_2026_10_20.md R1) ──

KO_T1 = ('#execute 온라인 강좌에서 같은 질문이 반복됩니다. 자료를 보고 FAQ 초안을 만들어 주세요.\n'
         '자료는 /Users/x/Desktop/AI/indiebizOS/outputs/long_sentence_imagination/2026-10-20_84회차/inputs 에 있는 '
         '사본이고 README.md가 색인이야. 산출물은 /Users/x/Desktop/AI/indiebizOS/outputs/long_sentence_imagination/'
         '2026-10-20_84회차/ai/ai_execute 폴더에 저장해 줘.')
WRAPPED = '<turn_context note="이번 턴 한정 부속 참고 정보.">\n# 현재 시각\n2026-10-20 10:51\n' + ('한국어 배경 자료 ' * 80) + '\n</turn_context>\n\n'


def _settings_of(cmd):
    import json
    return json.loads(cmd[cmd.index('--settings') + 1]) if '--settings' in cmd else None


@pytest.mark.parametrize('message, expected', [
    (KO_T1, 'Korean'),                                      # 경로가 길어도 발화는 한국어
    (WRAPPED + KO_T1, 'Korean'),                            # turn_context 뒤 본문으로 판정
    (WRAPPED + '#execute Please summarize the FAQ draft in three lines.', None),   # 배경은 한국어, 발화는 영어
    ('#execute Fix the failing test in backend/test_x.py', None),
    ('#execute 테스트', None),                                # 글자 수 미달 → 판정 보류
    ('', None),
])
def test_output_language_follows_the_users_utterance(message, expected):
    assert ClaudeCodeProvider.output_language_for(message) == expected


def test_language_key_rides_native_hook_settings_only_on_tool_turns():
    provider = ClaudeCodeProvider(api_key='', model='test', system_prompt='test')
    provider._binary_path = 'claude'
    provider._turn_message = WRAPPED + KO_T1
    settings = _settings_of(provider._build_command(mcp_config_path='/tmp/example.json'))
    assert settings['language'] == 'Korean' and 'hooks' in settings
    provider._turn_message = '#execute Fix the failing test in backend/test_x.py'
    settings = _settings_of(provider._build_command(mcp_config_path='/tmp/example.json'))
    assert 'language' not in settings and 'hooks' in settings
    # 원샷(tools_mode)·resume 은 종전대로: 원샷엔 --settings 자체가 없고, resume 은 같은 규칙
    provider._turn_message = KO_T1
    assert _settings_of(provider._build_command(tools_mode='none')) is None
    resumed = provider._build_command(mcp_config_path='/tmp/example.json', resume_session_id='prior')
    assert _settings_of(resumed)['language'] == 'Korean' and '--resume' in resumed


def test_process_message_stream_records_turn_message_before_build(monkeypatch):
    provider = ClaudeCodeProvider(api_key='', model='test', system_prompt='test')
    provider._binary_path = 'claude'
    provider._client = None          # 초기화 전 조기 반환 경로 — 턴 상태 초기화는 그보다 먼저다
    list(provider.process_message_stream(KO_T1, history=[]))
    assert provider._turn_message == KO_T1


def _normal_command(monkeypatch, *, door, supervised):
    monkeypatch.setattr('repair_context.active', lambda: False)
    monkeypatch.setattr('research_context.library_only', lambda: False)
    monkeypatch.setattr('supervision_bus.current', lambda *a, **kw: object() if supervised else None)
    monkeypatch.setattr(ClaudeCodeProvider, 'shell_door', classmethod(lambda cls: door))
    provider = ClaudeCodeProvider(api_key='', model='test', system_prompt='test')
    provider._binary_path = 'claude'
    provider.agent_role = 'execution'
    provider.agent_id = 'worker'
    cmd = provider._build_command(mcp_config_path='/tmp/example.json')
    pick = lambda flag: cmd[cmd.index(flag) + 1].split(',')
    return provider, pick('--tools'), pick('--allowed-tools'), pick('--disallowed-tools')


def test_body_door_replaces_native_shell_with_the_body_shell(monkeypatch):
    """자기 Bash는 명령이 끝날 때까지 모델을 붙잡는다. 기본 문은 Bash를 내리고 몸의 셸을 준다(에피소드 6178)."""
    provider, tools, allowed, denied = _normal_command(monkeypatch, door='body', supervised=True)
    for native in ClaudeCodeProvider.NATIVE_SHELL_TOOLS:
        assert native not in tools and native not in allowed and native in denied
    assert COMMAND in allowed and COMMAND not in denied
    assert {'Read', 'Write', 'Edit', 'Grep'} <= set(tools)          # 바로 끝나는 도구는 그대로다
    assert ClaudeCodeProvider.BODY_SHELL_POLICY in provider.tool_policy()


@pytest.mark.parametrize('door,supervised', [('native', True), ('body', False)])
def test_native_shell_stays_when_the_door_is_native_or_the_turn_has_no_workbench(monkeypatch, door, supervised):
    """몸의 셸은 감독 작업대를 거쳐 닿는다. 작업대가 없는 턴과 'native' 설정에서는 예전 그대로다."""
    provider, tools, allowed, denied = _normal_command(monkeypatch, door=door, supervised=supervised)
    assert 'Bash' in tools and 'Bash' in allowed and 'Bash' not in denied
    assert COMMAND not in allowed and COMMAND in denied
    assert ClaudeCodeProvider.BODY_SHELL_POLICY not in provider.tool_policy()


def test_changing_the_door_starts_a_fresh_cli_session(monkeypatch):
    """이어 가던 세션은 옛 도구 목록과 안내를 기억한다. 문이 바뀌면 세션 키가 달라져야 한다."""
    monkeypatch.setattr(ClaudeCodeProvider, 'shell_door', classmethod(lambda cls: 'body'))
    body = ClaudeCodeProvider.tool_policy_fingerprint()
    monkeypatch.setattr(ClaudeCodeProvider, 'shell_door', classmethod(lambda cls: 'native'))
    assert ClaudeCodeProvider.tool_policy_fingerprint() != body


def test_shell_door_reads_the_setting_and_defaults_to_body(tmp_path, monkeypatch):
    import json
    import world_pulse
    path = tmp_path / 'world_pulse_config.json'
    monkeypatch.setattr(world_pulse, 'PULSE_CONFIG_PATH', path)
    assert ClaudeCodeProvider.shell_door() == 'body'                 # 파일 없음
    path.write_text(json.dumps({'executor': {'claude_code_shell': 'native'}}))
    assert ClaudeCodeProvider.shell_door() == 'native'
    path.write_text(json.dumps({'executor': {'claude_code_shell': 'anything-else'}}))
    assert ClaudeCodeProvider.shell_door() == 'body'
