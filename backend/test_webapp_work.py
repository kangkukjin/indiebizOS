"""웹앱 검사는 호스트 앱의 개발 환경을 상속하지 않는다."""
import boot_paths  # noqa: F401
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('name,expected', [('build', 'production'), ('test', None)])
def test_check_process_has_task_environment(tmp_path, monkeypatch, name, expected):
    spec = importlib.util.spec_from_file_location('webapp_work_env', ROOT / 'data/scripts/webapp_work.py')
    work = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(work)
    monkeypatch.setattr(work, 'LOG_ROOT', tmp_path / 'logs')
    monkeypatch.setenv('NODE_ENV', 'development')
    command = 'import os,json;print(json.dumps([os.getenv("NODE_ENV"),os.getenv("CI")]))'
    (tmp_path / 'webapp-checks.json').write_text(json.dumps({'checks': [
        {'name': name, 'argv': [sys.executable, '-c', command]},
    ]}))
    plan = work.plan(tmp_path, [name])
    result = work.run_check(tmp_path, name, 10, plan['fingerprint'])
    assert result['ok'], result
    assert json.loads(result['output_tail']) == [expected, 'true']
    assert os.environ['NODE_ENV'] == 'development'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
