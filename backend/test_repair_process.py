"""Repair toolchain writes stay inside the OS sandbox on the first attempt."""
import boot_paths  # noqa: F401
from pathlib import Path
import pytest


@pytest.mark.parametrize('readonly', [False, True])
def test_go_cache_and_temp_are_inside_runtime(tmp_path, monkeypatch, readonly):
    from repair_process import prepare
    monkeypatch.setattr('repair_runtime.node_runtime', lambda *args: None)
    monkeypatch.setattr('runtime_utils.get_base_path', lambda: str(tmp_path))
    monkeypatch.setattr('repair_process.sandbox_command', lambda *args, **kwargs: args[0])
    source = {'GOCACHE': '/unwritable/build', 'GOMODCACHE': '/unwritable/mod',
              'GOTMPDIR': '/unwritable/tmp'}
    _, env = prepare(['go', 'test', './...'], tmp_path, env=source,
                     runtime=tmp_path / 'runtime', readonly=readonly)
    for key in ('GOCACHE', 'GOMODCACHE', 'GOTMPDIR'):
        assert Path(env[key]).is_relative_to(Path(env['TMPDIR']))
    assert Path(env['GOTMPDIR']).is_dir()
    assert source['GOCACHE'] == '/unwritable/build'


@pytest.mark.system
def test_first_go_test_runs_inside_real_repair_sandbox(tmp_path):
    import os
    import shutil
    from coding_process import available
    from repair_process import run
    go = shutil.which('go')
    if not go or not available():
        pytest.skip('requires Go and macOS repair sandbox')
    (tmp_path / 'go.mod').write_text('module repairprobe\n\ngo 1.20\n')
    (tmp_path / 'probe_test.go').write_text(
        'package repairprobe\nimport "testing"\n'
        'func TestCache(t *testing.T) { if 2+2 != 4 { t.Fatal("wrong") } }\n')
    env = dict(os.environ, GOTOOLCHAIN='local', GOPROXY='off', GOSUMDB='off',
               GOCACHE='/unwritable/build', GOTMPDIR='/unwritable/tmp')
    result = run([go, 'test', './...'], tmp_path, env=env, timeout=180)
    assert result.returncode == 0, result.stderr
    assert 'ok' in result.stdout and 'repairprobe' in result.stdout


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
