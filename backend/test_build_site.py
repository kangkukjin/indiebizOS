"""프로덕션 웹 빌드의 환경 계약."""
import boot_paths  # noqa: F401
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('analyze', [False, True])
def test_production_build_overrides_host_environment(tmp_path, monkeypatch, analyze):
    path = ROOT / 'data/packages/installed/tools/web-builder/tools/build_site.py'
    spec = importlib.util.spec_from_file_location('web_build_env', path)
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    (tmp_path / 'package.json').write_text(json.dumps({'scripts': {'build': 'build'}}))
    monkeypatch.setenv('NODE_ENV', 'development')
    calls = []

    def command(argv, **kwargs):
        calls.append(kwargs['env'])
        return {'success': True, 'stdout': ''}

    monkeypatch.setattr(builder, 'run_command', command)
    assert builder.run(str(tmp_path), analyze=analyze)['success']
    assert calls[0]['NODE_ENV'] == 'production'
    if analyze:
        assert calls[0]['ANALYZE'] == 'true'
    assert os.environ['NODE_ENV'] == 'development'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
