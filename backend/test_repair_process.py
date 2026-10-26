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


def test_bytecode_cache_prefix_is_inside_runtime(tmp_path, monkeypatch):
    from repair_process import prepare
    monkeypatch.setattr('repair_runtime.node_runtime', lambda *args: None)
    monkeypatch.setattr('runtime_utils.get_base_path', lambda: str(tmp_path))
    monkeypatch.setattr('repair_process.sandbox_command', lambda *args, **kwargs: args[0])
    _, env = prepare(['python3', '-m', 'pytest'], tmp_path, env={}, runtime=tmp_path / 'runtime')
    assert Path(env['PYTHONPYCACHEPREFIX']).is_relative_to(Path(env['TMPDIR']))
    assert env['PYTHONDONTWRITEBYTECODE'] == '1'


@pytest.mark.system
def test_stale_bytecode_next_to_source_is_not_executed(tmp_path):
    """같은 크기·같은 mtime 으로 바뀐 소스(긴문장 98회차 변형 B)는 소스 옆 __pycache__ 가 옛 바이트코드를
    돌려준다. 수리 검사 프로세스는 그 캐시를 읽지 않고 현재 소스를 실행해야 한다(L98-2)."""
    import os
    import subprocess
    import sys
    from coding_process import available
    from repair_process import run
    if not available():
        pytest.skip('requires macOS repair sandbox')
    module = tmp_path / 'subject_mod.py'
    module.write_text('def f():\n    return 1\n')
    stat = module.stat()
    env = {k: v for k, v in os.environ.items() if k not in ('PYTHONDONTWRITEBYTECODE', 'PYTHONPYCACHEPREFIX')}
    subprocess.run([sys.executable, '-c', 'import subject_mod'], cwd=tmp_path, env=env, check=True)
    assert list((tmp_path / '__pycache__').glob('subject_mod*.pyc'))
    module.write_text('def f():\n    return 2\n')
    os.utime(module, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    stale = subprocess.run([sys.executable, '-c', 'import subject_mod; print(subject_mod.f())'],
                           cwd=tmp_path, env=env, capture_output=True, text=True)
    assert stale.stdout.strip() == '1'          # 함정 재현: 일반 실행은 옛 바이트코드
    result = run([sys.executable, '-c', 'import subject_mod; print(subject_mod.f())'], tmp_path, env=env, timeout=120)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == '2'
