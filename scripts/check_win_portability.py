#!/usr/bin/env python3
"""윈도우 이식성 정적 검사 — 유닉스 전용 stdlib 의 무가드 톱레벨 import 탐지.

왜: `import fcntl` 이 톱레벨에 있으면 윈도우에서 *모듈 로드 자체*가 죽어
그 모듈이 받치는 서브시스템 전체가 500 이 된다(2026-07-20 윈도우 첫 설치에서
portal_core/bulletin_core 실측). 이 부류는 실행이 아니라 파싱으로 잡을 수 있다 —
AST 로 훑으므로 의존성 설치가 필요 없고, 맥·리눅스·윈도우 어디서든 돈다.

허용(플래그하지 않음):
  - try/except 안의 import        (ImportError 폴백 — portal_core 패턴)
  - if 분기 안의 import           (sys.platform 가드)
  - 함수/메서드 안의 lazy import  (유닉스 경로에서만 호출되는 함수)

둘째 검사 — 진입점 import 순서 (임베디드 파이썬 등가):
배포 임베디드 파이썬(python311._pth, isolated)은 스크립트 폴더를 sys.path 에
넣지 않아, api.py 가 자기 `sys.path.insert(BACKEND_PATH)` 보다 앞에서 backend
로컬 모듈을 톱레벨 import 하면 맥(표준 파이썬=sys.path[0]가 스크립트 폴더)에선
멀쩡하고 윈도우 설치앱에서만 기동이 죽는다(v1.3.6 `import mime_compat` 실측,
a70260c 에서 수정). 이 부류도 파싱으로 잡는다.

대상: backend/ + data/packages/installed/ (윈도우 설치본에 실리는 실행 코드).
pre-commit 훅과 CI(portability.yml) 양쪽에서 호출된다.
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 유닉스 전용 표준 모듈 (윈도우 CPython 에 없음)
UNIX_ONLY = {
    "fcntl", "pwd", "grp", "termios", "tty", "pty", "posix",
    "resource", "curses", "readline", "syslog", "crypt", "nis", "spwd",
}

SCAN_ROOTS = [ROOT / "backend", ROOT / "data" / "packages" / "installed"]
SKIP_DIRS = {"__pycache__", "_archive", "node_modules", ".git"}

# 서브트리 전체가 "가드됨"으로 간주되는 컨테이너
_GUARDS = (ast.Try, ast.If, ast.FunctionDef, ast.AsyncFunctionDef)


def _flag_imports(node: ast.AST, guarded: bool, out: list):
    for child in ast.iter_child_nodes(node):
        child_guarded = guarded or isinstance(node, _GUARDS)
        if isinstance(child, ast.Import):
            for alias in child.names:
                top = alias.name.split(".")[0]
                if top in UNIX_ONLY and not child_guarded:
                    out.append((child.lineno, top))
        elif isinstance(child, ast.ImportFrom):
            top = (child.module or "").split(".")[0]
            if top in UNIX_ONLY and not child_guarded:
                out.append((child.lineno, top))
        _flag_imports(child, child_guarded, out)


def scan_file(path: Path):
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as e:
        # 파싱 불가는 이 검사의 관할 밖 — 경고만 (문법은 py_compile/CI 빌드가 잡음)
        print(f"[warn] parse skip {path.relative_to(ROOT)}: {e.__class__.__name__}")
        return []
    out: list = []
    _flag_imports(tree, guarded=False, out=out)
    return out


# ── 진입점 import 순서 검사 (임베디드 파이썬 등가) ──────────────────────────
# 임베디드 파이썬으로 직접 기동되는 스크립트 — sys.path 부트스트랩 전에
# backend 로컬 모듈을 톱레벨 import 하면 안 된다.
ENTRYPOINTS = [ROOT / "backend" / "api.py"]


def _backend_local_names() -> set:
    """backend/ 직속 모듈·패키지 이름 — 진입점이 path 부트스트랩 후에만 import 가능한 것들."""
    backend = ROOT / "backend"
    names = {p.stem for p in backend.rglob("*.py")}
    names |= {p.name for p in backend.iterdir()
              if p.is_dir() and (p / "__init__.py").exists()}
    names.discard("api")
    return names


def _has_sys_path_bootstrap(node: ast.AST) -> bool:
    """노드 서브트리에 sys.path.insert/append 호출이 있는가."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            f = sub.func
            if (isinstance(f, ast.Attribute) and f.attr in ("insert", "append")
                    and isinstance(f.value, ast.Attribute) and f.value.attr == "path"
                    and isinstance(f.value.value, ast.Name) and f.value.value.id == "sys"):
                return True
    return False


def check_entrypoint_import_order():
    """진입점 톱레벨에서 sys.path 부트스트랩보다 앞선 backend 로컬 import 를 플래그.

    톱레벨 직속 문장만 순서대로 본다 — try/if 컨테이너 안 import 는 가드된 것으로
    간주(첫째 검사와 같은 문화). 부트스트랩 이후의 import 는 전부 허용.
    """
    local_names = _backend_local_names()
    flagged = []
    for entry in ENTRYPOINTS:
        if not entry.exists():
            continue
        try:
            tree = ast.parse(entry.read_text(encoding="utf-8"), filename=str(entry))
        except (SyntaxError, UnicodeDecodeError) as e:
            print(f"[warn] parse skip {entry.relative_to(ROOT)}: {e.__class__.__name__}")
            continue
        for node in tree.body:
            if _has_sys_path_bootstrap(node):
                break  # 부트스트랩 이후는 관할 밖
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top in local_names:
                        flagged.append((entry.relative_to(ROOT), node.lineno, top))
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                top = (node.module or "").split(".")[0]
                if top in local_names:
                    flagged.append((entry.relative_to(ROOT), node.lineno, top))
    return flagged


def main() -> int:
    flagged = []
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            for lineno, mod in scan_file(path):
                flagged.append((path.relative_to(ROOT), lineno, mod))

    order_flagged = check_entrypoint_import_order()

    failed = False
    if flagged:
        failed = True
        print("[FAIL] 유닉스 전용 모듈의 무가드 톱레벨 import — 윈도우에서 모듈 로드가 죽습니다:")
        for rel, lineno, mod in flagged:
            print(f"  {rel}:{lineno}  import {mod}")
        print()
        print("고치는 법: try/except ImportError 폴백(portal_core.py 참조), sys.platform 분기,")
        print("또는 유닉스 전용 코드 경로의 함수 안으로 lazy import.")

    if order_flagged:
        failed = True
        print("[FAIL] 진입점에서 sys.path 부트스트랩 전 backend 로컬 import — "
              "윈도우 임베디드 파이썬(_pth isolated)은 스크립트 폴더를 sys.path 에 안 넣어 기동이 죽습니다:")
        for rel, lineno, mod in order_flagged:
            print(f"  {rel}:{lineno}  import {mod}  (sys.path.insert 보다 앞)")
        print()
        print("고치는 법: 해당 import 를 sys.path.insert(0, str(BACKEND_PATH)) 뒤로 이동"
              "(v1.3.7 a70260c 의 mime_compat 수정 참조).")

    if failed:
        return 1

    print("[OK] 윈도우 이식성 정적 검사 통과 (유닉스 전용 무가드 import 없음 + 진입점 import 순서 정상)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
