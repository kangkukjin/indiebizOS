"""메모리 import 초기화도 격리 런타임의 저장소를 따른다."""
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest


def test_worker_owns_a_separate_runtime_from_its_parent(tmp_path, monkeypatch):
    from conftest import pytest_configure, pytest_unconfigure
    parent = tmp_path / 'parent'
    parent.mkdir()
    with monkeypatch.context() as patch:
        for key in ('INDIEBIZ_RUNTIME_STATE_DIR', 'INDIEBIZ_RUNTIME_STATE_DIR_TEST_OWNED',
                    'INDIEBIZ_RECALL_INDEX_DIR'):
            patch.setenv(key, str(parent))
        config = SimpleNamespace()
        pytest_configure(config)
        child = Path(config._runtime_state_root)
        try:
            assert child != parent and child.is_dir()
            assert os.environ['INDIEBIZ_RUNTIME_STATE_DIR'] == str(child)
            pytest_configure(config)
            assert config._runtime_state_root == str(child)
        finally:
            pytest_unconfigure(config)
        assert parent.is_dir() and not child.exists()


@pytest.mark.parametrize('location', ['runtime', 'userdata', 'base'])
def test_initialization_respects_storage_precedence(tmp_path, location):
    base = tmp_path / 'base'
    userdata = tmp_path / 'userdata'
    runtime = tmp_path / 'runtime'
    env = dict(os.environ, INDIEBIZ_BASE_PATH=str(base))
    env.pop('INDIEBIZ_USERDATA', None)
    env.pop('INDIEBIZ_RUNTIME_STATE_DIR', None)
    if location in ('runtime', 'userdata'):
        env['INDIEBIZ_USERDATA'] = str(userdata)
    if location == 'runtime':
        env['INDIEBIZ_RUNTIME_STATE_DIR'] = str(runtime)
    backend = Path(__file__).resolve().parent
    code = (
        'import sys,json; sys.path.insert(0,sys.argv[1]); import boot_paths; '
        'import system_ai_memory as m; '
        'print(json.dumps([str(m.MEMORY_DB_PATH), str(m.SYSTEM_MEMO_PATH)]))'
    )
    result = subprocess.run([sys.executable, '-c', code, str(backend)],
                            env=env, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
    expected = {'runtime': runtime, 'userdata': userdata, 'base': base / 'data'}[location]
    assert json.loads(result.stdout.splitlines()[-1]) == [
        str(expected / 'system_ai_memory.db'), str(expected / 'system_ai_memo.txt')]
    assert (expected / 'system_ai_memory.db').is_file()
    for other in {runtime, userdata, base / 'data'} - {expected}:
        assert not (other / 'system_ai_memory.db').exists()


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
