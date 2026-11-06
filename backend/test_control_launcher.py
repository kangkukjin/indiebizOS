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
import control_launcher
def capture(executable, args, env):
    assert args[1] == {str(control_base.base_dir(base, cid) / 'backend/services/restart_controller.py')!r}, args
    assert 'restart_controller' not in sys.modules
    print('approved-fallback-exec')
control_launcher._exec_controller = capture
control_launcher.launch({str(checkout)!r}, ['start'])
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


@pytest.mark.parametrize("exit_code", [0, 23])
def test_node_pipe_launcher_waits_and_preserves_child_io_and_exit(tmp_path, exit_code):
    """Exercise the Windows spawn path with the same pipe owner as Electron."""
    import control_launcher

    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for the Electron pipe integration test")
    folder = tmp_path / "한글 spaced folder"
    folder.mkdir()
    child = folder / "child.py"
    child.write_text(
        "import json,os,sys,time\n"
        "time.sleep(.15)\n"
        "print(json.dumps([sys.argv[1:], sys.stdin.read(), os.environ['LAUNCH_TEST']]))\n"
        "print('child stderr', file=sys.stderr)\n"
        f"raise SystemExit({exit_code})\n", encoding="utf-8")
    args = ['', 'two words', '한글 폴더', 'quote"inside', 'space and slash\\']
    launcher = folder / "launcher.py"
    launcher.write_text(f'''
import importlib.util, os, sys, types
spec = importlib.util.spec_from_file_location('launcher', {control_launcher.__file__!r})
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
# Also exercise the Windows path on macOS/Linux, using their real subprocess.
m.os = types.SimpleNamespace(name='nt')
m._exec_controller(sys.executable, [sys.executable, {str(child)!r}, *{args!r}],
                   dict(os.environ, LAUNCH_TEST='inherited'))
''', encoding="utf-8")
    script = '''
const {spawn} = require('node:child_process');
const child = spawn(process.argv[1], [process.argv[2]], {stdio:['pipe','pipe','pipe']});
let stdout='', stderr='';
child.stdout.on('data', data => stdout += data);
child.stderr.on('data', data => stderr += data);
child.on('error', error => {console.error(error); process.exitCode=1;});
child.on('close', (code, signal) => console.log(JSON.stringify({code, signal, stdout, stderr})));
child.stdin.end('pipe input');
'''
    result = subprocess.run([node, '-e', script, sys.executable, str(launcher)],
                            capture_output=True, text=True, encoding="utf-8", timeout=20,
                            env={**os.environ, 'PYTHONUTF8': '1'})
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt['code'] == exit_code and receipt['signal'] is None
    assert json.loads(receipt['stdout']) == [args, 'pipe input', 'inherited']
    assert receipt['stderr'].strip() == 'child stderr'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
