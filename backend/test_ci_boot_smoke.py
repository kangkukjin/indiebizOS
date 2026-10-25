"""Boot smoke owns only the processes it starts and verifies."""
import boot_paths  # noqa: F401
import importlib.util
import json
from pathlib import Path
import sys
import time

from restart_process import alive, identity

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
                   'Path("child.json").write_text(json.dumps(child.pid))\n'
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


if __name__ == "__main__":
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
