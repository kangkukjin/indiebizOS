"""Preflight protects whole scripts and reaches the executing model without a readback."""
import boot_paths  # noqa: F401
import json
import subprocess
from types import SimpleNamespace

import pytest
from command_preflight import check, blocked
from test_situation_evidence import active, module  # noqa: F401


def test_windows_default_and_explicit_dialect_selection(monkeypatch):
    import command_preflight as cp
    monkeypatch.setattr(cp, 'os', SimpleNamespace(name='nt', environ={'COMSPEC': r'C:\Windows\cmd.exe'}))
    source = "Write-Output '한글'"
    assert cp.default_argv(source)[0] == 'powershell'
    assert cp.default_argv(source)[-1].endswith(source)
    assert cp.default_argv(source, 'pwsh')[0] == 'pwsh'
    assert cp.default_argv('echo %TEMP%', 'cmd') == [r'C:\Windows\cmd.exe', '/d', '/s', '/c', 'echo %TEMP%']
    with pytest.raises(ValueError):
        cp.default_argv(source, 'unknown')
    with pytest.raises(ValueError):
        cp.default_argv(source, 'sh')


def test_cmd_actual_failure_reaches_protected_context(active):
    from preflight_feedback import execution_result
    from api_supervision import situation_context
    report = check(['cmd.exe', '/c', 'missing-command'])
    result = execution_result(report, 9009, "'missing-command' is not recognized")
    assert result['phase'] == 'execution' and result['executed'] is True
    assert result['coverage']['syntax'] == 'unsupported'
    context = situation_context('executor', 'situation-test')['context']
    assert 'SHELL_EXIT_NONZERO' in context and '9009' in context and 'missing-command' in context


def test_sync_command_passes_explicit_shell_and_publishes_actual_failure(active, tmp_path, monkeypatch):
    command = module('essentials_command')
    import command_preflight as cp
    seen = []
    monkeypatch.setattr(cp, 'default_argv', lambda source, shell: seen.append(shell) or ['/bin/sh', '-c', source])
    h = SimpleNamespace(_staging_mod=lambda: SimpleNamespace(reload_forcing_violation=lambda *a: None),
                        _REPO_ROOT=None, is_dangerous_command=lambda _: False, _red_grant_active=lambda: False)
    result = command.execute_command(h, {'command': 'echo useful-error >&2; exit 7', 'shell': 'sh'}, str(tmp_path))
    assert seen == ['sh'] and '[exit code: 7]' in result
    from api_supervision import situation_context
    context = situation_context('executor', 'situation-test')['context']
    assert 'SHELL_EXIT_NONZERO' in context and 'useful-error' in context


@pytest.mark.parametrize('shell', ['/bin/sh', '/bin/bash', '/bin/zsh'])
def test_complete_parse_prevents_first_effect(tmp_path, shell):
    from pathlib import Path
    if not Path(shell).exists():
        pytest.skip('shell unavailable')
    source = "printf effect >> marker\nif true; then\n echo ok\n"
    rejected = check([shell, '-c', source], cwd=tmp_path)
    assert rejected['status'] == 'invalid' and rejected['executed'] is False
    assert not (tmp_path / 'marker').exists()
    assert check([shell, '-c', source + 'fi\n'], cwd=tmp_path)['status'] == 'valid'
    assert not (tmp_path / 'marker').exists()


def test_actual_dialect_not_login_shell(tmp_path, monkeypatch):
    monkeypatch.setenv('SHELL', '/bin/zsh')
    source = 'for item (one two) print -r -- $item'
    assert blocked(check(['/bin/sh', '-c', source], cwd=tmp_path))
    assert check(['/bin/zsh', '-c', source], cwd=tmp_path)['status'] == 'valid'


def test_unsupported_never_executes_and_failures_are_not_zero_errors(tmp_path):
    def forbidden(*args, **kwargs):
        raise AssertionError('unsupported parser executed')
    assert check(['cmd.exe', '/c', 'echo effect'], runner=forbidden)['status'] == 'unsupported'
    assert check(['python', '-c', 'print(1)'], runner=forbidden)['status'] == 'unsupported'
    assert check(['/missing/bash', '-c', 'echo hi'], cwd=tmp_path)['status'] == 'failed'
    assert check(['/bin/sh', '-c', 'x' * 65537], cwd=tmp_path)['status'] == 'failed'


def test_timeout_and_cancel(tmp_path):
    def expired(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 2)
    assert check(['/bin/sh', '-c', 'echo hi'], runner=expired)['status'] == 'failed'
    assert check(['/bin/sh', '-c', 'echo hi'], cancelled=lambda: True)['status'] == 'failed'


def test_production_command_blocks_before_any_effect(active, tmp_path):
    command = module('essentials_command')
    h = SimpleNamespace(_staging_mod=lambda: SimpleNamespace(reload_forcing_violation=lambda *a: None),
                        _REPO_ROOT=None, is_dangerous_command=lambda _: False, _red_grant_active=lambda: False)
    source = 'printf once >> marker\nif true; then\n echo OK\n'
    rejected = json.loads(command.execute_command(h, {'command': source}, str(tmp_path)))
    assert rejected['executed'] is False
    assert not (tmp_path / 'marker').exists()
    from api_supervision import situation_context
    assert 'SHELL_SYNTAX' in situation_context('executor', 'situation-test')['context']
    assert command.execute_command(h, {'command': source + 'fi\n'}, str(tmp_path)) == 'OK'
    assert (tmp_path / 'marker').read_text() == 'once'


def test_ibl_direct_diagnostics_and_proven_binding_repair(active, tmp_path, monkeypatch):
    from execution_situation import run_tool
    from ibl_v2_entry import handle_request
    from recovery_observation import configure
    from api_supervision import situation_context
    configure(active.situation)
    bad = {'code': '#!ibl edition=2\nreturn $subtotal + 3', 'edition': 2}
    result = run_tool('execute_ibl', bad, lambda: handle_request(bad, str(tmp_path)))
    assert result['executed'] is False and result['issues'][0]['code'] == 'UNBOUND'
    context = situation_context('executor', 'situation-test')['context']
    assert 'UNBOUND' in context and 'subtotal' in context
    unrelated = {'code': '#!ibl edition=2\nreturn 10', 'edition': 2}
    run_tool('execute_ibl', unrelated, lambda: handle_request(unrelated, str(tmp_path)))
    assert any(r['resolution'] == 'unresolved' for r in active.situation.recovery.view())
    fixed = {'code': '#!ibl edition=2\n$subtotal = 7\nreturn $subtotal + 3', 'edition': 2}
    good = run_tool('execute_ibl', fixed, lambda: handle_request(fixed, str(tmp_path)))
    assert good['value'] == 10
    assert all(r['resolution'] == 'verified' for r in active.situation.recovery.view())
    context = situation_context('executor', 'situation-test')['context']
    assert 'UNBOUND' not in context


def test_binding_repair_preserves_every_operation_and_return():
    from ibl_preflight_feedback import binding_repair
    old = {'source': 'return $x + 3', 'missing': ['x']}
    assert binding_repair(old, '$x = 7\nreturn $x + 3')
    assert not binding_repair(old, '$x = 7\nreturn $x + 4')
    assert not binding_repair(old, '$x = [self:exec]{command:"echo effect"}\nreturn $x + 3')


def test_session_rejection_creates_no_worker_or_effect(active, tmp_path):
    from process_sessions import start
    from coding_store import CodingStore
    db = CodingStore(tmp_path / 'store')
    result = start('echo effect > marker\nif true; then', str(tmp_path), db=db, sandbox=False)
    assert result['executed'] is False
    assert not db.list('process_session') and not (tmp_path / 'marker').exists()


def test_long_ibl_locations_keep_first_error_inline(active):
    from preflight_feedback import publish
    from api_supervision import situation_context
    publish({'phase': 'preflight', 'status': 'invalid', 'executed': False, 'source_hash': 'x',
             'language': 'ibl', 'total': 20, 'items': [
                 {'code': 'UNBOUND', 'severity': 'error', 'message': '정의되지 않은 값 ' * 200,
                  'location': {'line': 2, 'column': 8, 'source_hash': 'a' * 64, 'uri': 'x' * 3000}}
             ] * 20})
    context = situation_context('executor', 'situation-test')['context']
    assert 'UNBOUND' in context and 'omitted' in context


def test_claude_hook_checks_final_transformed_command(monkeypatch, tmp_path, capsys):
    import io
    import supervision_hook
    monkeypatch.setattr(supervision_hook, 'check', lambda: None)
    monkeypatch.setattr(supervision_hook, 'situation_context', lambda _: '')
    monkeypatch.setenv('CLAUDE_CODE_SHELL', '/bin/bash')
    monkeypatch.setattr('sys.argv', ['hook'])
    monkeypatch.setattr('sys.stdin', io.StringIO(json.dumps({'tool_name':'Bash', 'cwd':str(tmp_path),
                                                           'tool_input':{'command':'echo effect > marker\nif true; then'}})))
    assert supervision_hook.main() == 2
    assert 'SHELL_SYNTAX' in capsys.readouterr().err
    assert not (tmp_path / 'marker').exists()
