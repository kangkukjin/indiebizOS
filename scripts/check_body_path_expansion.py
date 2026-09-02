#!/usr/bin/env python3
"""check_body_path_expansion.py — 경로 펼침 단일 해소점 관문 (pre-commit, 2026-09-02).

IBL 표면(backend/ibl · system_tools_ibl · 패키지 도구)에서 경로 값을 `os.path.expanduser` /
`Path(...).expanduser()` 로 직접 펼치면 `~workspace/…` 토큰(runtime_utils.expand_body_path)이
그 자리에서만 조용히 안 먹는다 — 해소점이 30여 곳 산재해 있던 것이 토큰을 못 들이던 이유다.
규칙: 위 범위의 .py 에서 `.expanduser(` 호출 금지. 정당한 예외는 그 줄에 `# path-ok: <사유>`.

    check_body_path_expansion.py            # 위반이면 1
    check_body_path_expansion.py --files …  # 지정 파일만(시험용)
"""
import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCOPES = ("backend/ibl", "backend/cognition/system_tools_ibl.py", "data/packages/installed/tools")
_MARK = re.compile(r"#\s*path-ok:\s*\S")


def _targets(argv):
    if "--files" in argv:
        return [Path(x) for x in argv[argv.index("--files") + 1:]]
    out = []
    for sc in SCOPES:
        p = REPO_ROOT / sc
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            out += sorted(x for x in p.rglob("*.py") if "/_temp_" not in str(x))
    return out


def violations(path: Path):
    try:
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []
    lines = src.splitlines()
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "expanduser":
            line = lines[node.lineno - 1] if node.lineno - 1 < len(lines) else ""
            if not _MARK.search(line):
                bad.append((node.lineno, line.strip()[:110]))
    return bad


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    total = 0
    for f in _targets(argv):
        for ln, text in violations(f):
            total += 1
            try:
                rel = f.resolve().relative_to(REPO_ROOT)
            except ValueError:
                rel = f
            print(f"  {rel}:{ln}: {text}")
    if total:
        print(f"[body-path] ✗ 경로 직접 펼침 {total}곳 — runtime_utils.expand_body_path 로 (예외는 `# path-ok: <사유>`)")
        return 1
    print("[body-path] ✓ 경로 펼침 단일 해소점 OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
