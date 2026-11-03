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


@pytest.mark.parametrize('readonly', [False, True])
def test_nested_runtime_keeps_os_boundary_and_cleans_children(tmp_path, readonly):
    import os
    import sys
    from repair_process import run
    outside = tmp_path / 'outside'
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    backend = Path(__file__).resolve().parent
    inner = '''import os, tempfile
from pathlib import Path
p = Path(tempfile.mkdtemp())
assert p.is_relative_to(Path(os.environ['INDIEBIZ_REPAIR_RUNTIME']))
try:
    Path(%r).write_text('escape')
except PermissionError:
    pass
else:
    raise AssertionError('outside write allowed')
''' % str(outside)
    if readonly:
        inner += '''
try:
    Path('readonly-violation').write_text('bad')
except PermissionError:
    pass
else:
    raise AssertionError('readonly workspace write allowed')
'''
    script = f'''import sys, os
sys.path.insert(0, {str(backend)!r})
import boot_paths
from repair_process import run
from pathlib import Path
before = set(Path(os.environ['TMPDIR']).iterdir())
r = run([sys.executable, '-c', {inner!r}], {str(workspace)!r}, readonly={readonly!r})
assert r.returncode == 0, (r.stdout, r.stderr)
assert set(Path(os.environ['TMPDIR']).iterdir()) == before
'''
    result = run([sys.executable, '-c', script], workspace, timeout=60)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert not outside.exists()



def test_nested_concurrency_and_scope_rejection(tmp_path):
    import sys
    from repair_process import run
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    backend = Path(__file__).resolve().parent
    script = f'''import sys, os
sys.path.insert(0, {str(backend)!r})
import boot_paths
from repair_process import run
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
before = set(Path(os.environ['TMPDIR']).iterdir())
def child(n):
    return run([sys.executable, '-c', 'print(' + str(n) + ')'], {str(workspace)!r})
with ThreadPoolExecutor(2) as pool:
    results = list(pool.map(child, [1, 2]))
assert [r.stdout.strip() for r in results] == ['1', '2'], results
assert set(Path(os.environ['TMPDIR']).iterdir()) == before
try:
    run([sys.executable, '-c', 'print(1)'], {str(tmp_path)!r})
except PermissionError:
    pass
else:
    raise AssertionError('parent scope widened')
'''
    result = run([sys.executable, '-c', script], workspace, timeout=60)
    assert result.returncode == 0, result.stderr


def test_cancelled_parent_stops_nested_child_before_runtime_cleanup(tmp_path):
    import sys
    import psutil
    from repair_process import run
    backend = Path(__file__).resolve().parent
    child = 'import os,time; from pathlib import Path; Path("pid").write_text(str(os.getpid())); time.sleep(60)'
    script = f'''import sys
sys.path.insert(0, {str(backend)!r})
import boot_paths
from repair_process import run
run([sys.executable, '-c', {child!r}], {str(tmp_path)!r}, timeout=30)
'''
    def cancel():
        if (tmp_path / 'pid').exists():
            raise PermissionError('cancel nested probe')
    with pytest.raises(PermissionError, match='cancel nested probe'):
        run([sys.executable, '-c', script], tmp_path, check=cancel, timeout=40)
    assert not psutil.pid_exists(int((tmp_path / 'pid').read_text()))


@pytest.mark.system
def test_original_apply_failures_inside_readonly_parent_pytest():
    import sys
    from repair_process import run
    root = Path(__file__).resolve().parents[1]
    cases = ['backend/test_repair_training_harness.py::test_fixed_scope_contract_gates_real_apply[correct]',
             'backend/test_repair_receipt_flow.py::test_real_test_apply_and_completion_without_ai',
             'backend/test_episode4296_4306_repairs.py::test_semantic_mixed_check_and_visual_evidence_apply[check-1]']
    result = run([sys.executable, '-m', 'pytest', *cases, '-p', 'no:cacheprovider', '--tb=short'],
                 root, readonly=True, timeout=180)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert '3 passed' in result.stdout
