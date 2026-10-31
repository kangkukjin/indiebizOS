"""손상된 checkout 제어자를 import하지 않고 승인 기반으로 복구 기동한다."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import json
import time

import pytest
import boot_paths  # noqa: F401
import control_base


def test_broken_checkout_controller_launches_approved_base(tmp_path):
    source = Path(__file__).resolve().parents[1]
    base, checkout = tmp_path / 'state', tmp_path / 'checkout'
    cid, note = control_base.ensure(source, base, source)
    assert cid, note
    for src, _ in control_base._entries():
        target = checkout / src
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / src, target)
    (checkout / 'backend/services/restart_controller.py').write_text('def broken(:\n')
    script = f'''
import sys, os
sys.path.insert(0, {str(source / 'backend')!r})
import boot_paths
sys.path.insert(0, {str(checkout / 'backend/services')!r})
from control_launcher import launch
def capture(executable, args, env):
    assert args[1] == {str(control_base.base_dir(base, cid) / 'backend/services/restart_controller.py')!r}, args
    assert 'restart_controller' not in sys.modules
    print('approved-fallback-exec')
os.execve = capture
launch({str(checkout)!r}, ['start'])
'''
    env = dict(os.environ, INDIEBIZ_BASE_PATH=str(base))
    env.pop('INDIEBIZ_CONTROL_NO_BASE', None)
    result = subprocess.run([sys.executable, '-c', script], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'approved-fallback-exec' in result.stdout


def test_controller_exec_preserves_real_child_arguments(tmp_path):
    import control_launcher

    folder = tmp_path / '한글 space dir'
    folder.mkdir()
    child = folder / 'echo args.py'
    output = folder / 'child.json'
    child.write_text('import json,sys,pathlib\n'
                     'pathlib.Path(sys.argv[1]).write_text(json.dumps(sys.argv[2:]))\n')
    args = ['plain', '', 'two words', '한글 폴더', 'quote"inside',
            'space and slash\\', 'before\\"after', '\\', '"']
    loader = f'''
import importlib.util, sys, os
spec = importlib.util.spec_from_file_location('launcher', {control_launcher.__file__!r})
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
m._exec_controller(sys.executable, [sys.executable, {str(child)!r}, {str(output)!r}, *{args!r}], dict(os.environ))
'''
    result = subprocess.run([sys.executable, '-c', loader], capture_output=True, text=True, timeout=20)
    deadline = time.monotonic() + 5
    while not output.exists() and time.monotonic() < deadline:
        time.sleep(.05)
    assert result.returncode == 0, result.stderr
    assert output.exists(), result.stderr  # Windows exec 부모의 exit=0만으로 성공 처리하지 않는다.
    assert json.loads(output.read_text()) == args


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
