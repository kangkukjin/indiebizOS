"""Commit checks may overlap, but an unfinished or failed gate never commits."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import boot_paths  # noqa: F401
import pytest
from common.platform_utils import IS_WINDOWS, pid_alive


ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(IS_WINDOWS or not shutil.which('bash'),
                                reason='POSIX Git hook process lifecycle')


def wait_for(path):
    deadline = time.monotonic() + 10
    while not path.exists():
        assert time.monotonic() < deadline, f'No hook progress: {path}'
        time.sleep(.02)


@pytest.fixture
def hook(tmp_path):
    binary = tmp_path / 'bin'
    binary.mkdir()
    git = binary / 'git'
    git.write_text('#!/bin/sh\nif [ "$1" = diff ]; then\n'
                   'echo backend/base/example.py\nelse\necho "$HOOK_ROOT"\nfi\n')
    git.chmod(0o755)
    python = binary / 'python3'
    python.write_text(f'#!{sys.executable}\n' + '''
import os, signal, sys, time
from pathlib import Path
root = Path(os.environ['HOOK_ROOT'])
name = Path(sys.argv[1]).name
if name == 'build_ibl_nodes.py' and '--inputs-regex' in sys.argv:
    print('^backend/.*')
elif name == 'red_safety_selftest.py' and '--triggers-regex' in sys.argv:
    print('^not-selected$')
elif name == 'build_ibl_nodes.py':
    def stop(signum, frame):
        (root / 'terminated').touch()
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGTERM, stop)
    (root / 'builder-pid').write_text(str(os.getpid()))
    deadline = time.monotonic() + 15
    while not (root / 'release').exists():
        if time.monotonic() > deadline:
            raise SystemExit('build was not released')
        time.sleep(.02)
    print('BUILD DIAGNOSTIC', flush=True)
    (root / 'builder-finished').touch()
    raise SystemExit(int(os.environ.get('BUILD_FAILURE', '0')))
elif name == 'build_body_bundle.py':
    deadline = time.monotonic() + 10
    while not (root / 'builder-pid').exists():
        if time.monotonic() > deadline:
            raise SystemExit('build did not start concurrently')
        time.sleep(.02)
    (root / 'foreground-started').touch()
    raise SystemExit(int(os.environ.get('FOREGROUND_FAILURE', '0')))
else:
    print('CHECK ' + name)
''')
    python.chmod(0o755)
    processes = []

    def start(**overrides):
        env = {**os.environ, 'PATH': str(binary) + os.pathsep + os.environ['PATH'],
               'HOOK_ROOT': str(tmp_path), 'TMPDIR': str(tmp_path), **overrides}
        process = subprocess.Popen(['bash', str(ROOT / 'scripts/git-hooks/pre-commit')],
                                   cwd=tmp_path, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        processes.append(process)
        return process

    yield tmp_path, start
    (tmp_path / 'release').touch()
    for process in processes:
        if process.poll() is None:
            process.terminate()
        process.communicate(timeout=15)


@pytest.mark.parametrize('failure', ['0', '1'])
def test_overlap_waits_for_build_and_propagates_failure(hook, failure):
    root, start = hook
    process = start(BUILD_FAILURE=failure)
    wait_for(root / 'foreground-started')
    assert process.poll() is None
    assert not (root / 'builder-finished').exists()
    (root / 'release').touch()
    stdout, stderr = process.communicate(timeout=15)
    assert process.returncode == int(failure), stdout + stderr
    assert (root / 'builder-finished').exists()
    assert 'BUILD DIAGNOSTIC' in stdout + stderr
    assert ('IBL 정합성 OK' in stdout) == (failure == '0')
    assert not list(root.glob('indiebiz-ibl-check.*'))


def test_foreground_failure_reaps_unfinished_build(hook):
    root, start = hook
    process = start(FOREGROUND_FAILURE='1')
    stdout, stderr = process.communicate(timeout=15)
    assert process.returncode != 0, stdout + stderr
    assert (root / 'terminated').exists()
    assert not (root / 'builder-finished').exists()
    assert not pid_alive(int((root / 'builder-pid').read_text()))
    assert not list(root.glob('indiebiz-ibl-check.*'))


def test_interruption_reaps_unfinished_build(hook):
    root, start = hook
    process = start()
    wait_for(root / 'foreground-started')
    process.terminate()
    process.communicate(timeout=15)
    assert process.returncode != 0
    assert (root / 'terminated').exists()
    assert not list(root.glob('indiebiz-ibl-check.*'))


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
