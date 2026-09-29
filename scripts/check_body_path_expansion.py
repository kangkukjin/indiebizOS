#!/usr/bin/env python3
"""check_body_path_expansion.py — 경로 펼침 단일 해소점 관문 (pre-commit, 2026-09-02).

IBL 표면(backend/ibl · system_tools_ibl · 패키지 도구)에서 경로 값을 `os.path.expanduser` /
`Path(...).expanduser()` 로 직접 펼치면 `~workspace/…` 토큰(runtime_utils.expand_body_path)이
그 자리에서만 조용히 안 먹는다 — 해소점이 30여 곳 산재해 있던 것이 토큰을 못 들이던 이유다.
규칙 1: 위 범위의 .py 에서 `.expanduser(` 호출 금지. 정당한 예외는 그 줄에 `# path-ok: <사유>`.
규칙 2 (2026-09-29, 상상훈련 73회차 B73-6 밭 이관): 입력 dict 의 경로 인자(`path`·`file_path`·`output_path`…)를
  해소점 없이 파일 경로 자리(`Path(…)`·`os.path.join`·`abspath`·`realpath`·`exists`·`isfile`·`isdir`·`open`)에
  넣지 말 것. 규칙 1 은 **잘못 펼치는** 형태만 보고 **아예 펼치지 않는** 형태를 못 봤다 — 73회차
  `read_pdf`·`read_docx`·`sheet_ops._resolve` 가 `~workspace/…` 를 project_path 밑 글자 그대로 찾았다
  (같은 이름이 xlsx·html 에선 되고 pdf·docx 에선 not_found). 판정: 같은 함수 안에서 입력 경로 읽기
  (`d.get("path")`, `or` 사슬·`str()` 포함)를 받은 이름이 `expand_body_path`/`*resolve*`/`*expand*` 결과로
  다시 묶이지 않은 채 위 자리에 들어가면 위반. `.suffix`·`.name`·`.stem` 만 보는 쓰임은 경로 해석이 아니다.
  은퇴 코드(`_deprecated/`)는 스캔 밖.

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


_PATH_KEYS = {"path", "file_path", "src", "dir_path", "output", "output_path", "folder", "directory", "dest",
              "target", "file", "out", "source", "dst", "destination", "root", "base_path", "local_path",
              "image_path", "data_file"}
_INPUT_NAMES = {"tool_input", "ti", "params", "input_data", "args", "p", "inp", "tool_args"}
_SINKS = {"Path", "pathlib.Path", "os.path.join", "os.path.abspath", "os.path.realpath", "os.path.exists",
          "os.path.isfile", "os.path.isdir", "open"}
_NAME_ONLY = {"suffix", "name", "stem", "suffixes"}


def _raw_path_read(e) -> bool:
    if (isinstance(e, ast.Call) and isinstance(e.func, ast.Attribute) and e.func.attr == "get"
            and isinstance(e.func.value, ast.Name) and e.func.value.id in _INPUT_NAMES and e.args
            and isinstance(e.args[0], ast.Constant) and e.args[0].value in _PATH_KEYS):
        return True
    if isinstance(e, ast.BoolOp):
        return any(_raw_path_read(v) for v in e.values)
    if isinstance(e, ast.Call) and isinstance(e.func, ast.Name) and e.func.id == "str" and e.args:
        return _raw_path_read(e.args[0])
    return False


def _unresolved_joins(tree):
    """규칙 2 — (줄, 함수) 목록."""
    out = []
    parents = {id(c): n for n in ast.walk(tree) for c in ast.iter_child_nodes(n)}
    for fn in (n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))):
        raw, cleared = set(), set()
        assigns = [n for n in ast.walk(fn) if isinstance(n, ast.Assign) and len(n.targets) == 1
                   and isinstance(n.targets[0], ast.Name)]
        for n in assigns:
            if _raw_path_read(n.value):
                raw.add(n.targets[0].id)
        changed = True
        while changed:        # 해소점을 지난 값(또는 그런 이름을 쓰는 값)으로 다시 묶인 이름 — 흐름 무관 근사
            changed = False
            for n in assigns:
                name = n.targets[0].id
                if name in cleared:
                    continue
                for sub in ast.walk(n.value):
                    callee = ""
                    if isinstance(sub, ast.Call):
                        f = sub.func
                        callee = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
                    if ("expand" in callee or "resolve" in callee or callee == "_src_path"
                            or isinstance(sub, ast.Name) and sub.id in cleared):
                        cleared.add(name)
                        changed = True
                        break
        for n in ast.walk(fn):
            if not isinstance(n, ast.Call):
                continue
            try:
                name = ast.unparse(n.func)
            except Exception:
                continue
            if name not in _SINKS:
                continue
            up = parents.get(id(n))
            if isinstance(up, ast.Attribute) and up.attr in _NAME_ONLY:
                continue
            args = [a.args[0] if isinstance(a, ast.Call) and isinstance(a.func, ast.Name) and a.func.id == "str"
                    and a.args else a for a in n.args]
            if any(_raw_path_read(a) or (isinstance(a, ast.Name) and a.id in raw and a.id not in cleared)
                   for a in args):
                out.append((n.lineno, fn.name))
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
    if "/_deprecated/" not in str(path):
        for ln, fname in _unresolved_joins(tree):
            line = lines[ln - 1] if ln - 1 < len(lines) else ""
            if not _MARK.search(line):
                bad.append((ln, f"[해소점 없는 입력 경로 · {fname}] {line.strip()[:90]}"))
    return sorted(set(bad))


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
        print(f"[body-path] ✗ 경로 직접 펼침·해소점 없는 입력 경로 {total}곳 — runtime_utils.expand_body_path 로 "
              f"(예외는 `# path-ok: <사유>`)")
        return 1
    print("[body-path] ✓ 경로 펼침 단일 해소점 OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
