"""Update lifecycle stops before mutations and never guesses process ownership."""
import boot_paths  # noqa: F401
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import remote_update_runtime as lifecycle
from restart_protocol import atomic_json, control_dir
from update_maintenance import check_start, maintenance_path


def test_stopped_install_stays_stopped_and_maintenance_blocks_other_starts(tmp_path):
    receipt = lifecycle.quiesce(tmp_path, 'test')
    assert receipt['phase'] == 'stopped' and receipt['backend'] is False
    with pytest.raises(ValueError, match='Source update'):
        check_start(tmp_path)
    with pytest.raises(ValueError, match='Another update'):
        lifecycle.quiesce(tmp_path, 'other')
    lifecycle.guard(tmp_path, 'test')
    result = lifecycle.resume(tmp_path, 'test', '')
    assert result['surface'] == 'stopped'
    assert not maintenance_path(tmp_path).exists()
    check_start(tmp_path)


def test_admission_token_only_permits_the_recorded_start_phase(tmp_path):
    atomic_json(maintenance_path(tmp_path), {'phase': 'stopped', 'token': 'permit'})
    with pytest.raises(ValueError):
        check_start(tmp_path, {'INDIEBIZ_UPDATE_TOKEN': 'permit'})
    atomic_json(maintenance_path(tmp_path), {'phase': 'starting', 'token': 'permit'})
    with pytest.raises(ValueError):
        check_start(tmp_path, {'INDIEBIZ_UPDATE_TOKEN': 'other'})
    check_start(tmp_path, {'INDIEBIZ_UPDATE_TOKEN': 'permit'})


def test_actual_checkout_process_blocks_mutation_but_other_checkout_does_not(tmp_path):
    other = tmp_path / 'other'
    other.mkdir()
    (other / 'backend').mkdir()
    api = other / 'backend/api.py'
    api.write_text('import time; time.sleep(60)')
    p = subprocess.Popen([sys.executable, str(api)])
    try:
        lifecycle.stopped(tmp_path)
        with pytest.raises(ValueError, match='still running'):
            lifecycle.stopped(other)
        assert p.poll() is None  # inspection never terminates anything
    finally:
        p.terminate()
        p.wait(timeout=5)


def test_unresolvable_argv_operand_does_not_abort_process_scan(tmp_path, monkeypatch):
    # Windows: resolving \\.\pipe\... argv of another app raises WinError 231.
    real_resolve = Path.resolve

    def resolve(self, *a, **kw):
        if 'pipe' in self.parts:
            raise OSError(231, 'All pipe instances are busy')
        return real_resolve(self, *a, **kw)

    monkeypatch.setattr(Path, 'resolve', resolve)
    assert lifecycle._arg_paths(tmp_path, ['--flag', 'pipe/x', 'api.py']) == [str(tmp_path / 'api.py')]


def test_process_scan_ignores_pipe_operand_but_still_finds_target_backend(tmp_path, monkeypatch):
    from types import SimpleNamespace
    root = tmp_path.resolve()
    real_resolve = Path.resolve

    def resolve(self, *args, **kwargs):
        if 'pipe' in self.parts:
            raise OSError(231, 'All pipe instances are busy')
        return real_resolve(self, *args, **kwargs)

    def process(pid, argv):
        return SimpleNamespace(pid=pid, cmdline=lambda: argv, cwd=lambda: str(root),
                               exe=lambda: str(root / 'python.exe'))

    monkeypatch.setattr(Path, 'resolve', resolve)
    monkeypatch.setattr(lifecycle.psutil, 'process_iter', lambda: iter([
        process(70001, ['chrome', 'pipe/chrome.nativeMessaging']),
        process(70002, ['python', 'pipe/unrelated', 'backend/api.py']),
        process(70003, ['python', str(root / 'other/backend/api.py')]),
    ]))
    monkeypatch.setattr(lifecycle, 'identity', lambda pid: {'pid': pid, 'born': 1})
    assert lifecycle.processes(root) == [
        {'identity': {'pid': 70002, 'born': 1}, 'desktop': False, 'launcher': False}]
    with pytest.raises(ValueError, match='still running; no files changed: 70002'):
        lifecycle.stopped(root)


def test_legacy_desktop_and_controller_are_rejected_before_maintenance(tmp_path, monkeypatch):
    monkeypatch.setattr(lifecycle, 'processes', lambda root: [{'identity': {'pid': 999999, 'born': 1}, 'desktop': True}])
    with pytest.raises(ValueError, match='no update handshake'):
        lifecycle.quiesce(tmp_path, 'test')
    assert not maintenance_path(tmp_path).exists()
    monkeypatch.setattr(lifecycle, 'processes', lambda root: [])
    monkeypatch.setattr(lifecycle, 'alive', lambda ident: bool(ident))
    atomic_json(control_dir(tmp_path) / 'state.json', {'controller': {'pid': 999999, 'born': 1}})
    with pytest.raises(ValueError, match='lacks graceful'):
        lifecycle.quiesce(tmp_path, 'test')
    assert not maintenance_path(tmp_path).exists()


def test_stale_desktop_receipt_cannot_authorize_closing_a_reused_pid(tmp_path):
    atomic_json(lifecycle.desktop_path(tmp_path), {'schema': 1, 'root': str(tmp_path), 'pid': 77,
                'nonce': 'previous', 'mode': 'dev', 'started_at': 100})
    with pytest.raises(ValueError, match='stale'):
        lifecycle.desktop_receipt(tmp_path, [{'identity': {'pid': 77, 'born': 200}, 'desktop': True}])


def test_rejected_controller_shutdown_preserves_original_running_state_on_retry(tmp_path, monkeypatch):
    rows = [{'identity': {'pid': 999999, 'born': 1}, 'desktop': False}]
    monkeypatch.setattr(lifecycle, 'processes', lambda root: rows)
    monkeypatch.setattr(lifecycle, 'alive', lambda ident: bool(ident))
    atomic_json(control_dir(tmp_path) / 'state.json', {'controller': {'pid': 999999, 'born': 1}})
    with pytest.raises(ValueError, match='lacks graceful'):
        lifecycle.quiesce(tmp_path, 'retry')
    first = lifecycle.load(tmp_path, 'retry')
    assert first['backend'] is True and first['before'] == rows
    rows.clear()
    atomic_json(control_dir(tmp_path) / 'state.json', {})
    second = lifecycle.quiesce(tmp_path, 'retry')
    assert second['phase'] == 'stopped' and second['backend'] is True
    assert second['before'] == first['before']
    assert second['first_observed_at'] == first['first_observed_at']


def test_unknown_original_desktop_cannot_be_reported_as_stopped_installation(tmp_path, monkeypatch):
    rows = [{'identity': {'pid': 999999, 'born': 1}, 'desktop': True}]
    monkeypatch.setattr(lifecycle, 'processes', lambda root: rows)
    with pytest.raises(ValueError, match='no update handshake'):
        lifecycle.quiesce(tmp_path, 'desktop')
    rows.clear()
    second = lifecycle.quiesce(tmp_path, 'desktop')
    assert second['desktop_unresolved'] and second['before']
    with pytest.raises(ValueError, match='restoration is unverified'):
        lifecycle.verify(tmp_path, second)


def test_interrupted_start_is_observed_and_never_spawned_again(tmp_path, monkeypatch):
    value = lifecycle.quiesce(tmp_path, 'test')
    value.update(phase='starting', backend=True)
    lifecycle.save(tmp_path, value)
    lifecycle.marker(tmp_path, value)
    monkeypatch.setattr(lifecycle.subprocess, 'Popen', lambda *a, **k: pytest.fail('duplicate launch'))
    monkeypatch.setattr(lifecycle, 'verify', lambda *a: (_ for _ in ()).throw(TimeoutError('pending')))
    with pytest.raises(TimeoutError):
        lifecycle.resume(tmp_path, 'test', '')
    assert maintenance_path(tmp_path).exists()
    with pytest.raises(ValueError, match='not quiesced'):
        lifecycle.guard(tmp_path, 'test')


def test_guard_prevents_later_steps_when_a_process_appears(tmp_path, monkeypatch):
    lifecycle.quiesce(tmp_path, 'test')
    monkeypatch.setattr(lifecycle, 'processes', lambda root: [{'identity': {'pid': 77, 'born': 1}}])
    with pytest.raises(ValueError, match='still running'):
        lifecycle.guard(tmp_path, 'test')


def test_retry_start_refuses_live_process_and_retains_launch_evidence(tmp_path, monkeypatch):
    value = lifecycle.quiesce(tmp_path, 'test')
    value.update(phase='starting', launch={'pid': 77, 'born': 1})
    lifecycle.save(tmp_path, value)
    lifecycle.marker(tmp_path, value)
    monkeypatch.setattr(lifecycle, 'processes', lambda root: [{'identity': value['launch']}])
    with pytest.raises(ValueError, match='still running'):
        lifecycle.retry_start(tmp_path, 'test', '')
    assert lifecycle.load(tmp_path, 'test')['launch'] == value['launch']


@pytest.mark.system
def test_live_work_drains_then_updated_backend_is_restored(request, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import test_restart_process as process_tests
    from restart_process import alive
    from restart_protocol import request as control_request
    # Use the same real controller + HTTP worker fixture as restart failure tests.
    source = process_tests.SERVER.replace(
        'from fastapi import FastAPI',
        '''import sys
if __name__ == '__main__' and os.environ.get('INDIEBIZ_MANAGED_WORKER') != '1':
    import boot_paths
    from restart_controller import main
    raise SystemExit(main(code_root=Path(__file__).resolve().parents[1]))
from fastapi import FastAPI''').replace(
        '{"status": "healthy", "live_turns": []}',
        '{"status": "healthy", "live_turns": [], "base_path": os.environ["INDIEBIZ_BASE_PATH"]}')
    monkeypatch.setattr(process_tests, 'SERVER', source)
    base, port, _, state = request.getfixturevalue('runtime')
    monkeypatch.setenv('INDIEBIZ_API_PORT', str(port))
    monkeypatch.setenv('INDIEBIZ_PRODUCTION', '1')
    before = state()
    with ThreadPoolExecutor(max_workers=1) as pool:
        work = pool.submit(process_tests.http, port, '/work?seconds=1.5', payload={}, timeout=10)
        process_tests.eventually(lambda: process_tests.ProcessAdapter(base, base, port).status(state()).get('active_roots', 0) > 0)
        lifecycle.quiesce(base, 'live', timeout=40)
        assert work.result()['finished'] is True
    assert (base / 'effects').read_text() == 'done\n'
    assert not alive(before['controller']) and not alive(before['worker'])
    with (base / 'backend/api.py').open('a') as stream:
        stream.write('\n# new source generation\n')
    result = lifecycle.resume(base, 'live', '', timeout=30)
    try:
        assert result['status'] == 'succeeded'
        assert state()['generation'] != before['generation']
        assert state()['code_digest'] != before['code_digest']
        assert state()['controller'] != before['controller']
        assert not maintenance_path(base).exists()
    finally:
        control_request(base, 'test_complete', operation='shutdown',
                        policy={'drain_before_shutdown': True, 'drain_timeout_s': 10, 'force': False})
        process_tests.eventually(lambda: state()['phase'] == 'STOPPED')
        process_tests.eventually(lambda: not alive(state()['controller']))


# Expose the existing process fixture without introducing a second runner.
from test_restart_process import runtime  # noqa: E402,F401


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
