"""회원 업데이트의 OS 코드 신원 검사를 기본 회귀 진입점에 연결한다."""
import boot_paths  # noqa: F401
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.system
def test_update_native_signature_and_lifecycle():
    if not shutil.which('node'):
        pytest.skip('Node 런타임이 필요합니다')
    root = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        ['node', '--test', 'member-desktop/test/updates.test.cjs',
         'member-desktop/test/native-signature.test.cjs'],
        cwd=root, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
