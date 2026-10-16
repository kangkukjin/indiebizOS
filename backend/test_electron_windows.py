"""실제 Electron의 ESM 로더로 주인 창 진입점 회귀를 검사한다."""
import boot_paths  # noqa: F401
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.system
def test_electron_window_entry():
    root = Path(__file__).resolve().parent.parent
    if not shutil.which("node") or not (root / "frontend/node_modules/electron").exists():
        pytest.skip("설치된 Node/Electron 런타임이 필요합니다")
    result = subprocess.run(
        ["node", "--test", "frontend/electron/windows.test.mjs"],
        cwd=root, capture_output=True, text=True, timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
