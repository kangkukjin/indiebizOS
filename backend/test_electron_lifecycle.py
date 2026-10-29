"""Launcher transport and native embedded-browser teardown contracts."""
import boot_paths  # noqa: F401
import json
import os
from pathlib import Path
import subprocess

import pytest
from common.platform_utils import host_os

ROOT = Path(__file__).resolve().parents[1]


def test_socket_generation_and_tab_session_lifetime():
    subprocess.run([
        'node', '--test', 'frontend/electron/launcher-connection.test.mjs',
        'frontend/electron/embedded-browser-tabs.test.mjs',
    ], cwd=ROOT, check=True, timeout=30, capture_output=True, text=True)


@pytest.mark.system
def test_real_electron_webview_teardown(tmp_path):
    if host_os() == 'linux' and not os.environ.get('DISPLAY'):
        pytest.skip('Native Electron requires a graphical session')
    frontend = ROOT / 'frontend'
    binary = subprocess.check_output(
        ['node', '-p', 'require("electron")'], cwd=frontend, text=True).strip()
    env = dict(os.environ, CRASH_TEST_PROFILE=str(tmp_path / 'profile'))
    env.pop('ELECTRON_RUN_AS_NODE', None)
    result = subprocess.run(
        [binary, str(frontend / 'scripts/embedded-browser-stress.cjs')],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=130)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report['cycles'] == 40
    for contract in ('snapshot', 'click', 'iframe', 'navigation',
                     'pendingCommandRemoval', 'ownedClose', 'navigatingRemoval', 'hostClose'):
        assert report[contract], report


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
