"""손상된 checkout 제어자를 import하지 않고 승인 기반으로 복구 기동한다."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

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


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
