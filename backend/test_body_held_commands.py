"""몸의 셸은 명령을 쥐고, 끝나거나 제한 시간이 지나면 돌아온다.

설계: docs/BODY_HELD_COMMANDS_DESIGN_2026_11_17.md. 계기: 에피소드 6178 — 실행자가 자기 명령 안의 `cat`에
걸려 19분을 기다렸고, 그동안 명령이 일하는 중인지 서 있는지 아는 주체가 없었다.
"""
import boot_paths  # noqa: F401
import importlib.util
import json
import shlex
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from coding_store import CodingStore

PACKAGE = Path(__file__).resolve().parents[1] / 'data/packages/installed/tools/system_essentials'


@pytest.fixture
def shell(tmp_path, monkeypatch):
    """패키지의 셸 도구를 임시 저장소 위에서 부른다. 남은 프로세스는 끝에서 거둔다."""
    import process_sessions
    db = CodingStore(tmp_path / 'store')
    monkeypatch.setattr(process_sessions, 'store', lambda: db)
    spec = importlib.util.spec_from_file_location('held_essentials_command', PACKAGE / 'essentials_command.py')
    command = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(command)
    handler = SimpleNamespace(
        is_dangerous_command=lambda text: text.startswith('rm '),
        _staging_mod=lambda: SimpleNamespace(reload_forcing_violation=lambda text, root: None),
        _REPO_ROOT=None, _red_grant_active=lambda: False, _load_sibling=lambda name: None)
    work = tmp_path / 'work'
    work.mkdir()

    def run(text, **params):
        return command.execute_command(handler, {'command': text, 'shell': 'sh', **params}, str(work))

    run.db, run.work = db, work
    yield run
    for row in db.list('process_session'):
        value = process_sessions.query(row['id'], db=db)
        if value['state'] in ('queued', 'running'):
            process_sessions.query(row['id'], db=db, op='control', action='cancel', request_id='teardown',
                                   generation=value['generation'])


def test_finished_command_keeps_the_text_it_always_returned(shell):
    assert shell('echo hi') == 'hi'
    assert shell('true') == '(명령어가 출력 없이 완료됨)'
    assert shell('echo out; echo err >&2; exit 3') == 'out\n\n[stderr]\nerr\n\n[exit code: 3]'
    assert shell.db.list('process_session') == []   # 끝난 명령은 기록을 남기지 않는다


def test_timeout_brings_the_caller_back_and_leaves_the_command_running(shell):
    """제한 시간은 '넘으면 죽인다'가 아니라 '넘으면 돌아온다'다. 돌아올 때 살아 있다는 신호가 함께 온다."""
    import process_sessions
    started = time.monotonic()
    result = json.loads(shell(f'{shlex.quote(sys.executable)} -u -c "import time; print(1, flush=True); time.sleep(60)"',
                              timeout=2))
    assert time.monotonic() - started < 8
    assert result['success'] is True and result['timed_out'] is True and result['state'] == 'running'
    assert result['output'] == '1' and result['task_ref']['kind'] == 'process'
    assert result['signs']['stdin'] == 'closed' and result['signs']['processes']
    assert '[self:task]' in result['note']
    # 같은 손잡이로 이어서 본다 — 명령은 죽지 않았다
    import task_receipts
    seen = task_receipts.status(result['task_ref'])
    assert seen['state'] == 'running' and seen['progress']['signs']['running_s'] >= result['signs']['running_s']
    process_sessions.task_cancel(result['task_ref'])
    deadline = time.monotonic() + 8
    while task_receipts.status(result['task_ref'])['state'] == 'running' and time.monotonic() < deadline:
        time.sleep(0.1)
    assert task_receipts.status(result['task_ref'])['state'] == 'cancelled'


def test_reader_of_input_does_not_wait_forever(shell):
    """6178의 꼴. 입력 통로를 닫고 시작하므로 `cat`은 곧바로 지나가고 뒤의 명령이 돈다."""
    started = time.monotonic()
    assert shell('cat >> /dev/null; echo passed', timeout=30) == 'passed'
    assert time.monotonic() - started < 10


def test_interactive_session_is_chosen_by_input_not_by_duration(shell):
    receipt = json.loads(shell('cat', mode='session', yield_ms=200))
    assert receipt['state'] == 'running' and receipt['capabilities']['input'] is True
    assert receipt['signs']['stdin'] == 'open'


def test_syntax_error_and_dangerous_command_never_start_a_process(shell):
    rejected = json.loads(shell('if then'))
    assert rejected['executed'] is False and not rejected.get('accepted')
    assert shell('rm -rf nothing') == '__REQUIRES_APPROVAL__:rm -rf nothing'
    assert shell.db.list('process_session') == []


def test_cli_door_runs_with_the_users_shell_path(shell, monkeypatch):
    import process_sessions
    monkeypatch.setattr(process_sessions, '_USER_SHELL', {'value': ('sh', '/indiebiz-user-bin:/usr/bin:/bin')})
    assert json.loads(shell('echo "$PATH"', _door='cli'))['output'].startswith('/indiebiz-user-bin:')
    assert '/indiebiz-user-bin' not in shell('echo "$PATH"')


def test_member_cannot_reach_the_owner_shell(shell):
    """회원의 셸은 회원 기기로 가는 다른 길이다. 이 문은 주인 전용이고, 거절은 프로세스가 뜨기 전에 난다."""
    import principal as P
    with P.narrow(P.member('A', 4, 'devA')):
        result = shell('echo should-not-run > leaked.txt')
    assert result.startswith('Error: 명령어 실행 실패') and '소유자' in result
    assert not (shell.work / 'leaked.txt').exists() and shell.db.list('process_session') == []


def test_cli_door_gets_an_envelope_and_the_bridge_unfolds_it_into_shell_text(shell):
    """CLI 실행자의 길: 감독 작업대는 봉투를 읽고, MCP 다리는 실행자에게 셸이 낸 글자 그대로 보인다."""
    import mcp_server
    ok = shell('printf "a\\nb\\n"', _door='cli')
    assert json.loads(ok) == {'shape': 'command', 'success': True, 'executed': True, 'state': 'succeeded',
                              'exit_code': 0, 'output': 'a\nb'}
    assert mcp_server._command_text(ok) == ('a\nb', False)
    assert mcp_server._command_text(shell('true', _door='cli')) == ('(명령어가 출력 없이 완료됨)', False)
    bad = shell('echo no; exit 4', _door='cli')
    assert json.loads(bad)['success'] is False
    assert mcp_server._command_text(bad) == ('no\n[exit code: 4]', True)
    running = shell(f'{shlex.quote(sys.executable)} -u -c "import time; print(7, flush=True); time.sleep(60)"',
                    _door='cli', timeout=2)
    text, failed = mcp_server._command_text(running)
    assert failed is False and text.startswith('7\n\n[아직 실행 중] ')
    status = json.loads(text.split('[아직 실행 중] ', 1)[1])
    assert status['state'] == 'running' and status['task_ref']['kind'] == 'process' and status['signs']['processes']
    # 다른 봉투(수리 명령의 결과, 지시 전달)는 다리가 손대지 않는다
    assert mcp_server._command_text('{"success": false, "not_executed": true}') is None
    assert mcp_server._command_text('plain text') is None


from test_conscious_supervisor import supervisor  # noqa: E402,F401


def test_ordinary_executor_reaches_a_real_process_through_the_workbench(supervisor, tmp_path, monkeypatch):
    """MCP 다리 뒤의 실제 길: 감독 작업대 → 셸 도구 → 몸이 쥔 프로세스. 호출은 몸의 기록에 남는다."""
    import api_supervision
    import process_sessions
    from providers.claude_code import ClaudeCodeProvider
    db = CodingStore(tmp_path / 'held-store')
    monkeypatch.setattr(process_sessions, 'store', lambda: db)
    monkeypatch.setattr(process_sessions, '_USER_SHELL', {'value': ('sh', '/usr/bin:/bin')})
    monkeypatch.setattr(ClaudeCodeProvider, 'shell_door', classmethod(lambda cls: 'body'))
    monkeypatch.setattr('repair_context.active', lambda: False)
    monkeypatch.setattr('research_context.library_only', lambda: False)
    done = api_supervision.dispatch('worker', supervisor.task, {'command': 'echo through', 'timeout': 10},
                                    repair_command=True)
    assert done == {'shape': 'command', 'success': True, 'executed': True, 'state': 'succeeded',
                    'exit_code': 0, 'output': 'through'}, done
    failed = api_supervision.dispatch('worker', supervisor.task, {'command': 'exit 9', 'timeout': 10},
                                      repair_command=True)
    assert failed['success'] is False and failed['exit_code'] == 9
    cost = supervisor.store.cost
    assert cost['execution_calls'] == 2 and cost['execution_failures'] == 1
    assert [row['name'] for row in supervisor.store.tool_index(limit=5)] == ['run_command', 'run_command']


def test_command_left_running_ends_with_its_turn(supervisor, tmp_path, monkeypatch):
    """제한 시간이 지나도 죽이지 않는 대신, 실행자가 두고 간 명령은 턴이 끝날 때 함께 끝난다."""
    import api_supervision
    import process_sessions
    from providers.claude_code import ClaudeCodeProvider
    db = CodingStore(tmp_path / 'held-store')
    monkeypatch.setattr(process_sessions, 'store', lambda: db)
    monkeypatch.setattr(process_sessions, '_USER_SHELL', {'value': ('sh', '/usr/bin:/bin')})
    monkeypatch.setattr(ClaudeCodeProvider, 'shell_door', classmethod(lambda cls: 'body'))
    monkeypatch.setattr('repair_context.active', lambda: False)
    monkeypatch.setattr('research_context.library_only', lambda: False)
    left = api_supervision.dispatch('worker', supervisor.task, {
        'command': f'{shlex.quote(sys.executable)} -c "import time; time.sleep(120)"', 'timeout': 1}, repair_command=True)
    kept = api_supervision.dispatch('worker', supervisor.task, {
        'command': f'{shlex.quote(sys.executable)} -c "import time; time.sleep(120)"', 'timeout': 1,
        'lifetime': 'session'}, repair_command=True)
    assert left['state'] == kept['state'] == 'running' and left['timed_out'] is True
    try:
        supervisor.close()
        deadline = time.monotonic() + 10
        state = lambda value: process_sessions.query(value['task_ref']['task_id'], db=db)['state']
        while state(left) == 'running' and time.monotonic() < deadline:
            time.sleep(0.1)
        assert state(left) == 'cancelled'
        assert state(kept) == 'running'          # 세션 수명으로 시작한 것은 턴을 넘겨 산다
    finally:
        process_sessions.task_cancel(kept['task_ref'])
