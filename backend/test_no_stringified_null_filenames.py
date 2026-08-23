"""저장소 안에 `None`·`null`·`undefined`·`nan` 이름의 파일이 있으면 실패.

2026-08-24 저장소 루트에 0바이트 `None` 파일이 생겼다(경로 변수가 None 인 채 문자열화되어
쓰인 침묵 오류). 작성자는 못 찾았지만, 부류는 확실하다 — 다음엔 생기자마자 잡는다.
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BAD = {"none", "null", "undefined", "nan", "nil"}
SKIP_DIRS = {".git", ".venv", "node_modules", "dist", "__pycache__", "_backups", "build", "release"}


def test_no_stringified_null_filenames():
    found = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for n in filenames:
            if n.lower() in BAD:
                found.append(os.path.relpath(os.path.join(dirpath, n), ROOT))
        for d in dirnames:
            if d.lower() in BAD:
                found.append(os.path.relpath(os.path.join(dirpath, d), ROOT) + "/")
    assert not found, f"문자열화된 null 이름의 파일 — 경로 변수가 None 인 채 쓰였다: {found}"


if __name__ == "__main__":
    import pytest as _pytest
    raise SystemExit(_pytest.main([__file__]))
