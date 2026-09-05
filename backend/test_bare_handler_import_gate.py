"""맨 `import handler` 금지 관문 (2026-09-05, Seam Guards CI 실측).

패키지 핸들러는 전부 파일명이 handler.py 다. 누가 sys.path 에 자기 패키지 폴더를 넣고 맨 이름으로 `import handler` 하면
sys.modules['handler'] 한 칸을 여러 패키지가 다투고, 뒤에 온 쪽은 **남의 모듈**을 받는다 — 시험 순서·프로세스 수명에 따라
결과가 달라지는 침묵 오염이다. CI 에서 notebook 시험 11건이 web 핸들러를 받아 AttributeError 로 죽었고, 로컬 단독 실행은
초록이라 아무도 보지 못했다(2026-09-03~09-05, Seam Guards 빨강 메일).

규약: 패키지 핸들러는 tool_loader 처럼 **고유 이름**으로 spec-load 한다(`tool_handler_<패키지>`). 이 관문은 backend/ 와
data/packages/ 의 파이썬 전수에서 맨 import 를 잡는다 — 동결 목록 없음(0 이어야 한다).
"""
import os
import re
import sys

import pytest

BACKEND = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BACKEND)
_BARE = re.compile(r"^\s*(?:import handler(?:\s+as\s+\w+)?\s*(?:#.*)?$|from handler import\b)", re.M)


def _py_files():
    for base in (os.path.join(ROOT, "backend"), os.path.join(ROOT, "data", "packages")):
        for cur, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", "pylibs", "node_modules", ".git")]
            for f in files:
                if f.endswith(".py"):
                    yield os.path.join(cur, f)


def test_no_bare_handler_import_anywhere():
    bad = []
    for p in _py_files():
        try:
            src = open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for m in _BARE.finditer(src):
            line = src.count("\n", 0, m.start()) + 1
            bad.append(f"{os.path.relpath(p, ROOT)}:{line}: {m.group(0).strip()}")
    assert not bad, ("맨 `import handler` — 패키지 핸들러는 고유 이름으로 spec-load 하세요(tool_loader 규약, "
                     "시험은 _pkg_handler 같은 로더):\n  " + "\n  ".join(bad))


def test_gate_regex_self_test():
    assert _BARE.search("    import handler as H\n")
    assert _BARE.search("import handler\n")
    assert _BARE.search("from handler import execute\n")
    assert not _BARE.search("import handler_utils\n")
    assert not _BARE.search("mod = _pkg_handler('notebook')\n")
    assert not _BARE.search("# import handler 는 금지\n")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
