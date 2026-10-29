"""봉인 제어 기반의 지연 import 수명: 정본 경로 없이 세대 정리 후 종료까지 검증."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import boot_paths  # noqa: F401
import control_base

ROOT = Path(__file__).resolve().parents[1]


def sealed_control(tmp_path):
    manifest = control_base.snapshot(ROOT, tmp_path)
    return control_base.base_dir(tmp_path, manifest['id'])


def run_isolated(code, *args):
    result = subprocess.run([sys.executable, '-I', '-B', '-c', code, *map(str, args)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def test_idle_shutdown_needs_no_episode_module(tmp_path):
    control = sealed_control(tmp_path)
    run_isolated('''
import sys
from pathlib import Path
control = Path(sys.argv[1])
sys.path[:0] = [str(control / 'backend/base'), str(control / 'backend/datastore')]
from restart_red import record_interrupted
record_interrupted(sys.argv[2], {'live_episode_ids': []}, 'intentional_shutdown')
assert 'episode_logger' not in sys.modules
''', control, tmp_path)
    assert not (tmp_path / 'data/world_pulse.db').exists()


@pytest.mark.parametrize('episode_ids', [[], [1]])
def test_sealed_controller_keeps_import_generation_until_process_ends(tmp_path, episode_ids):
    control = sealed_control(tmp_path)
    store = tmp_path / 'data/restart_control/generations'
    support = store / 'support'
    # Actual production modules, copied without tests or checkout path fallbacks.
    for path in (ROOT / 'backend').rglob('*.py'):
        if path.name.startswith('test_') or path.name == 'conftest.py' or '__pycache__' in path.parts:
            continue
        target = support / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    support.joinpath('manifest.json').write_text(json.dumps({'created_at': 0}))
    for n in range(1, 6):
        generation = store / str(n)
        generation.mkdir()
        generation.joinpath('manifest.json').write_text(json.dumps({'created_at': n}))
    control_base._seal(support)
    run_isolated('''
import sys, json, sqlite3
from pathlib import Path
control, base, support = map(Path, sys.argv[1:4])
ids = json.loads(sys.argv[4])
sys.path.insert(0, str(control / 'backend/base'))
from control_base import install_support_path, support_roots
install_support_path(control, support)
from restart_controller import Controller
assert 'episode_logger' not in sys.modules
ctl = Controller(base, base)
ctl.state.update(generation_dir=str(support.parent / '5'),
                 previous={'generation_dir': str(support.parent / '4')})
ctl._prune_generations()
assert support.exists(), '제어자의 import 기반을 회수했습니다'
assert not (support.parent / '1').exists(), '참조 없는 과거 세대는 정리해야 합니다'
assert support_roots() == (str(support),)
# The worker is already stopped; finish the same forced intentional shutdown as the incident.
class Stopped:
    def stop(self, state, force=False): pass
    def stopped(self, state): return True
ctl.adapter = Stopped()
ctl.state.update(phase='STOPPING', intentional=True, force=True, deadline=0,
                 last_owners={'live_episode_ids': ids, 'owners': []})
with sqlite3.connect(base / 'data/world_pulse.db') as conn:
    conn.executescript("CREATE TABLE episode_log(id INTEGER, ended_at TEXT, log TEXT);"
                       "INSERT INTO episode_log VALUES(1, NULL, 'request');")
ctl._tick_stopping()
assert ctl.state['phase'] == 'STOPPED'
with sqlite3.connect(base / 'data/world_pulse.db') as conn:
    ended, log = conn.execute('SELECT ended_at,log FROM episode_log').fetchone()
if ids:
    import episode_logger
    assert Path(episode_logger.__file__).is_relative_to(support)
    assert ended and '[Episode CUT]' in log
else:
    assert ended is None and log == 'request'
    assert 'episode_logger' not in sys.modules
''', control, tmp_path, support, json.dumps(episode_ids))
    # A new process no longer owns the previous controller's support generation.
    run_isolated('''
import sys
from pathlib import Path
control, base, support = map(Path, sys.argv[1:4])
sys.path.insert(0, str(control / 'backend/base'))
import control_base, generation_store
assert control_base.support_roots() == ()
generation_store.prune(support.parent, {support.parent / '5', support.parent / '4'})
assert not support.exists()
''', control, tmp_path, support)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
