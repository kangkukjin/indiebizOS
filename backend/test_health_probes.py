"""정본 검사와 실행 세대 환경의 경계를 검증한다."""
import subprocess
import sys
from pathlib import Path

import pytest
import boot_paths  # noqa: F401
import health_probes as probes


@pytest.mark.parametrize("name,script", [
    ("_run_import_coverage", "scripts/check_import_coverage.py"),
    ("_run_silent_failure_regression", "backend/test_ibl_v2_core.py"),
    ("_run_red_drift", "scripts/check_red_drift.py"),
])
def test_source_probes_keep_interpreter_without_worker_identity(tmp_path, monkeypatch, name, script):
    source = tmp_path / "source"
    for rel in (script, "backend/test_ibl_silent_failures.py", "backend/test_pipe_currency_failures.py"):
        path = source / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    monkeypatch.setenv("INDIEBIZ_CODE_ROOT", str(tmp_path / "generation"))
    monkeypatch.setenv("INDIEBIZ_RUNTIME_CONTROL", "private-token")
    monkeypatch.setenv("INDIEBIZ_MANAGED_WORKER", "1")
    seen = []

    def run(command, **kwargs):
        seen.append(command)
        assert command[0] == sys.executable
        assert kwargs["cwd"] == str(source)
        assert kwargs["env"]["INDIEBIZ_CODE_ROOT"] == str(source)
        assert "INDIEBIZ_RUNTIME_CONTROL" not in kwargs["env"]
        assert "INDIEBIZ_MANAGED_WORKER" not in kwargs["env"]
        return subprocess.CompletedProcess(command, 0, '@@IMPORT_COVERAGE_JSON@@ {"ok": true}', '')

    monkeypatch.setattr(subprocess, "run", run)
    result = getattr(probes, name)(source)
    assert result["success"] is True
    if name == "_run_import_coverage":
        assert seen[0][-2:] == ["--venv", sys.executable]
    if name == "_run_silent_failure_regression":
        assert len(seen) == 3


def test_missing_source_suite_is_still_failure(tmp_path):
    result = probes._run_silent_failure_regression(tmp_path)
    assert result["success"] is False
    assert "backend/test_ibl_v2_core.py 없음" == result["error_message"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
