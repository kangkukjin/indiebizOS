"""Cleanup is an observation, never a replacement for the primary failure."""
import os
import sys
import pytest
import script_process


def test_timeout_retains_output_when_group_cleanup_is_denied(tmp_path, monkeypatch):
    monkeypatch.setattr(script_process.os, 'killpg', lambda *args: (_ for _ in ()).throw(PermissionError(1, 'denied')))
    result = script_process.run_process([sys.executable, '-u', '-c',
        'import time; print("PARTIAL", flush=True); time.sleep(60)'], b'',
        cwd=tmp_path, env=os.environ.copy(), timeout=.2)
    assert result['timed_out'] and 'PARTIAL' in result['stdout']
    assert result['cleanup']['confirmed'] is False
    assert result['cleanup']['diagnostics'][0]['phase'] == 'cleanup'


def test_cancel_retains_primary_exception_and_partial_output(tmp_path):
    import time
    deadline = time.monotonic() + .2
    def check():
        if time.monotonic() > deadline:
            raise PermissionError('cancelled by owner')
    with pytest.raises(PermissionError, match='cancelled by owner') as caught:
        script_process.run_process([sys.executable, '-u', '-c',
            'import time; print("PARTIAL", flush=True); time.sleep(60)'], b'',
            cwd=tmp_path, env=os.environ.copy(), timeout=10, check=check)
    assert 'PARTIAL' in caught.value.process_result['stdout']
