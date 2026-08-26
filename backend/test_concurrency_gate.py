"""동시성 규율 관문(check_concurrency) 다리 시험 — 잠금 대기·워커 스레드 수명 선언.

동시성 밭 폐쇄(2026-08-27): 기록된 부류(싱글턴 레이스·워커 스레드 리로드 사멸·
유령 워커)는 각각 수리·정본화됐지만 탄생 관문이 없었다. 판정 가능한 3부류를 가드한다
— [A] sqlite3.connect timeout 미선언 [B] 패키지(리로드 워커) 안 Thread 수명 미선언
[C] check_same_thread=False 잠금 설계 미선언.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CHECKER = ROOT / "scripts" / "check_concurrency.py"


@pytest.fixture(scope="module")
def checker():
    spec = importlib.util.spec_from_file_location("cc_checker", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gate_passes_on_current_tree():
    proc = subprocess.run([sys.executable, str(CHECKER)],
                          capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_gate_has_teeth(checker, tmp_path):
    bad = tmp_path / "p.py"
    bad.write_text(
        "import sqlite3, threading\n"
        "conn = sqlite3.connect('x.db')\n"                                  # [A]
        "conn2 = sqlite3.connect('x.db', timeout=10, check_same_thread=False)\n"  # [C]
        "t = threading.Thread(target=print)\n")                             # [B] — 패키지 경로일 때만
    hits_backend = checker._scan_file(bad, "backend/services/p.py")
    assert {h[2] for h in hits_backend} == {"A", "C"}
    hits_pkg = checker._scan_file(bad, "data/packages/installed/tools/x/p.py")
    assert {h[2] for h in hits_pkg} == {"A", "B", "C"}


def test_gate_respects_declarations(checker, tmp_path):
    good = tmp_path / "q.py"
    good.write_text(
        "import sqlite3, threading\n"
        "conn = sqlite3.connect('x.db', timeout=10)\n"
        "t = threading.Thread(target=print)  # cc-ok: 짧은 병렬 — join 봉인\n")
    assert checker._scan_file(good, "data/packages/installed/tools/x/q.py") == []
    bare = tmp_path / "r.py"
    bare.write_text("import threading\nt = threading.Thread(target=print)  # cc-ok\n")
    assert len(checker._scan_file(bare, "data/packages/installed/tools/x/r.py")) == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
