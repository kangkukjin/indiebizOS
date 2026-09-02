"""개인 명사 관문 회귀 — 이름은 목록(로컬)에, 관문은 몸(저장소)에 (2026-09-02).

실측: 저장소가 public 인데 가족 이름·목소리 키가 추적 파일 56곳(어휘 fixture·가이드·패키지
기본값·시험 문자열·마이그레이션)에 박혀 있었다 — 사람이 눈으로 거르던 자리였다.

고정하는 계약: 목록의 정규식이 걸리면 실패 · allow 글롭은 면제 · 바이너리는 건너뜀 ·
목록이 없으면 보이게 생략(0) · 목록 파일 자체는 검사하지 않음.

실행: .venv/bin/python -m pytest backend/test_private_nouns_gate.py -q
"""
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATE = os.path.join(ROOT, "scripts", "check_private_nouns.py")


def _run(*args):
    r = subprocess.run([sys.executable, GATE, *args], capture_output=True, text=True, cwd=ROOT)
    return r.returncode, r.stdout + r.stderr


@pytest.fixture
def listfile(tmp_path):
    p = tmp_path / "nouns.txt"
    p.write_text("# 시험 목록\n홍길동\n(?<![A-Za-z])abc[0-9]*(?![A-Za-z])\nallow: *_signed.md\n", encoding="utf-8")
    return p


def test_hit_fails_and_names_the_line(listfile, tmp_path):
    f = tmp_path / "body.py"
    f.write_text("x = 1\nname = '홍길동'\n", encoding="utf-8")
    code, out = _run("--list", str(listfile), "--files", str(f))
    assert code == 1 and "body.py:2" in out


def test_regex_boundary_and_allow_glob(listfile, tmp_path):
    ok = tmp_path / "ok.py"; ok.write_text("token = 'xabc'  # 단어 경계 밖\n", encoding="utf-8")
    bad = tmp_path / "bad.py"; bad.write_text("key = 'abc3'\n", encoding="utf-8")
    signed = tmp_path / "paper_signed.md"; signed.write_text("저자 홍길동\n", encoding="utf-8")
    assert _run("--list", str(listfile), "--files", str(ok))[0] == 0
    assert _run("--list", str(listfile), "--files", str(bad))[0] == 1
    assert _run("--list", str(listfile), "--files", str(signed))[0] == 0


def test_binary_skipped_and_missing_list_is_visible_skip(listfile, tmp_path):
    b = tmp_path / "blob.bin"; b.write_bytes(b"\x00\x01" + "홍길동".encode("utf-8"))
    assert _run("--list", str(listfile), "--files", str(b))[0] == 0
    code, out = _run("--list", str(tmp_path / "없음.txt"), "--files", str(b))
    assert code == 0 and "검사 생략" in out


def test_hook_wires_the_gate():
    hook = open(os.path.join(ROOT, "scripts", "git-hooks", "pre-commit"), encoding="utf-8").read()
    assert "check_private_nouns.py" in hook
    ignore = open(os.path.join(ROOT, ".gitignore"), encoding="utf-8").read()
    assert "data/private_nouns.txt" in ignore.splitlines()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
