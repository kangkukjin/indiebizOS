"""데스크톱 시작의 서버 식별·재사용·실패·소유 수명을 실 소켓으로 검사한다."""
import boot_paths  # noqa: F401
from pathlib import Path
import shutil
import subprocess

import pytest


def test_electron_dev_lifecycle():
    root = Path(__file__).resolve().parent.parent
    if not shutil.which("node") or not (root / "frontend/node_modules/vite").exists():
        pytest.skip("설치된 Node/Vite 런타임이 필요합니다")
    result = subprocess.run(
        ["node", "--test", "frontend/scripts/electron-dev.test.mjs"],
        cwd=root, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
