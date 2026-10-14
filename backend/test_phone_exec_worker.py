"""Run the actual phone Python worker in disposable host processes (not Android proof)."""
import boot_paths  # noqa: F401
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
PHONE = ROOT / 'phone-companion/app/src/main/python'


def run(tmp_path, command):
    work = tmp_path / 'work'
    work.mkdir(exist_ok=True)
    request = tmp_path / 'request.json'
    request.write_text(json.dumps({'command': command, 'workspace': str(work), 'base_path': str(ROOT)}))
    subprocess.run([sys.executable, '-c', 'from phone_exec_worker import run; import sys; run(sys.argv[1])', str(request)],
                   env={**os.environ, 'PYTHONPATH': str(PHONE)}, check=True, timeout=8)
    return json.loads((tmp_path / 'result.json').read_text())


def test_python_json_and_unicode_stdout(tmp_path):
    result = run(tmp_path, {'op': 'python', 'code': 'print("삼성1")\nresult = {"value": inputs["n"] * 2}', 'inputs': {'n': 3}})
    assert result['success'] and result['value'] == {'value': 6}
    assert result['stdout'] == '삼성1\n' and result['stderr'] == ''
    assert result['exit_code'] is None


def test_shell_input_env_and_exit_status(tmp_path):
    result = run(tmp_path, {'op': 'shell', 'cmd': 'cat; printf "$WORD" >&2; exit 7', 'stdin': '입력\n', 'env': {'WORD': '오류'}})
    assert result['stdout'] == '입력\n' and result['stderr'] == '오류'
    assert not result['success'] and result['exit_code'] == 7


@pytest.mark.parametrize('source, error', [('raise PermissionError("denied")', 'PermissionError'), ('result = {1, 2}', 'TypeError')])
def test_python_errors_preserve_traceback(tmp_path, source, error):
    result = run(tmp_path, {'op': 'python', 'code': source})
    assert not result['success'] and result['exception_type'] == error
    assert 'Traceback' in result['stderr']


def test_large_output_and_value_are_file_references(tmp_path):
    result = run(tmp_path, {'op': 'python', 'code': 'print("a" * 9000000)\nresult = "값" * 40000'})
    assert result['success'] and result['output_truncated']
    assert len(result['stdout']) == 65536
    assert sum(x['size'] for x in result['artifacts']) == 8 * 1024 * 1024
    assert json.loads(Path(result['value_ref']['path']).read_text()) == '값' * 40000


def test_shell_timeout_terminates_background_group(tmp_path):
    result = run(tmp_path, {'op': 'shell', 'cmd': 'sleep 30 & wait', 'timeout': 1})
    assert result['timeout'] and not result['success']


def test_native_and_subprocess_output_are_captured(tmp_path):
    result = run(tmp_path, {'op': 'python', 'code': '''import os, subprocess
os.write(1, b"native")
subprocess.run(["/bin/sh", "-c", "printf child >&2"], check=True)'''})
    assert result['success'] and result['stdout'] == 'native' and result['stderr'] == 'child'
    assert not result['diagnostics_incomplete']


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
