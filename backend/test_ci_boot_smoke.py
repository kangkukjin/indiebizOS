"""Boot smoke owns only the processes it starts and verifies."""
import boot_paths  # noqa: F401
import importlib.util
import io
import json
from pathlib import Path
import sys
import time

import pytest
import psutil

from restart_process import ProcessAdapter, alive, identity, signal_owned

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('boot_smoke_under_test', ROOT / 'scripts/ci_boot_smoke.py')
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


def test_existing_live_worker_prevents_spawn_and_cleanup(tmp_path, monkeypatch):
    monkeypatch.setenv('INDIEBIZ_BASE_PATH', str(tmp_path))
    monkeypatch.setattr(smoke, 'controller_state', lambda base: {'worker': {'pid': 44, 'born': 10}})
    monkeypatch.setattr(smoke, 'alive', lambda value: bool(value))
    monkeypatch.setattr(smoke.subprocess, 'Popen', lambda *a, **k: (_ for _ in ()).throw(AssertionError('spawned')))
    assert smoke.main() == 2


def test_smoke_reaps_actual_spawned_tree(tmp_path, monkeypatch):
    (tmp_path / 'backend').mkdir()
    api = tmp_path / 'backend/api.py'
    api.write_text('import subprocess,sys,time,json\nfrom pathlib import Path\n'
                   'child=subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"])\n'
                   'Path("child.tmp").write_text(json.dumps(child.pid))\n'
                   'Path("child.tmp").replace("child.json")\n'
                   'time.sleep(30)\n')
    monkeypatch.setenv('INDIEBIZ_BASE_PATH', str(tmp_path))
    monkeypatch.setattr(smoke, 'ROOT', str(tmp_path))
    monkeypatch.setattr(smoke, 'API_PY', str(api))
    monkeypatch.setattr(smoke, '_python', lambda: sys.executable)
    observed = []

    def observe(base, root, controller, **kwargs):
        path = tmp_path / 'backend/child.json'
        deadline = time.monotonic() + 10
        while not path.exists() and time.monotonic() < deadline:
            time.sleep(.02)
        child = identity(json.loads(path.read_text()))
        observed.extend([controller, child])
        return {'status': 'succeeded', 'controller': controller, 'worker': child}

    monkeypatch.setattr(smoke, 'wait_for_boot', observe)
    assert smoke.main() == 0
    deadline = time.monotonic() + 5
    while any(alive(member) for member in observed) and time.monotonic() < deadline:
        time.sleep(.02)
    assert all(not alive(member) for member in observed)


@pytest.mark.parametrize('launcher_identity_missing', [False, True])
def test_smoke_follows_and_reaps_controller_after_launcher_exit(
        tmp_path, monkeypatch, launcher_identity_missing):
    """Real processes reproduce Windows exec: launcher exits, controller lives."""
    backend = tmp_path / 'backend'
    backend.mkdir()
    child_script = backend / 'controller.py'
    child_script.write_text(
        'import json,os,time\nfrom pathlib import Path\n'
        'Path("child.tmp").write_text(json.dumps(os.getpid()))\n'
        'Path("child.tmp").replace("child.json")\ntime.sleep(30)\n')
    api = backend / 'api.py'
    api.write_text('import subprocess,sys\n'
                   'subprocess.Popen([sys.executable,"controller.py"])\n')
    monkeypatch.setenv('INDIEBIZ_BASE_PATH', str(tmp_path))
    monkeypatch.setattr(smoke, 'ROOT', str(tmp_path))
    monkeypatch.setattr(smoke, 'API_PY', str(api))
    monkeypatch.setattr(smoke, '_python', lambda: sys.executable)
    if launcher_identity_missing:
        def gone(pid):
            raise psutil.NoSuchProcess(pid)
        monkeypatch.setattr(smoke, 'identity', gone)
    observed = []
    real_wait = smoke.wait_for_boot

    def observe(base, root, controller, **kwargs):
        path = backend / 'child.json'
        deadline = time.monotonic() + 10
        while (not path.exists() or alive(controller)) and time.monotonic() < deadline:
            time.sleep(.02)
        assert path.exists() and not alive(controller)
        child = identity(json.loads(path.read_text()))
        observed.append(child)
        import remote_boot
        assert remote_boot._launch_matches(child, kwargs['launch_token'])
        assert not remote_boot._launch_matches(child, 'another-launch')
        assert not remote_boot._launch_matches({**child, 'born': child['born'] - 1},
                                               kwargs['launch_token'])
        state = {'controller': child, 'worker': child, 'phase': 'ACTIVE',
                 'generation': 'test', 'code_digest': 'test'}
        dest = tmp_path / 'data/restart_control/state.json'
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(state))
        adapter = ProcessAdapter(base, root)
        adapter.status = lambda _: {'generation': 'test', 'code_digest': 'test',
                                    'ownership': 'known', 'readiness': 'ready'}
        class Opener:
            def open(self, *args, **kwargs):
                return io.BytesIO(json.dumps({'status': 'healthy', 'base_path': str(base)}).encode())
        adapter.opener = Opener()
        kwargs.update(adapter=adapter, timeout=1, interval=.02)
        result = real_wait(base, root, controller, **kwargs)
        assert kwargs['launch_token'] not in json.dumps(result)
        return result

    monkeypatch.setattr(smoke, 'wait_for_boot', observe)
    try:
        assert smoke.main() == 0
        deadline = time.monotonic() + 5
        while any(alive(member) for member in observed) and time.monotonic() < deadline:
            time.sleep(.02)
        assert observed and all(not alive(member) for member in observed)
    finally:
        # Also clean up a child if an assertion fails before smoke owns it.
        path = backend / 'child.json'
        if path.exists():
            try:
                signal_owned(identity(json.loads(path.read_text())), force=True)
            except psutil.NoSuchProcess:
                pass


if __name__ == "__main__":
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
