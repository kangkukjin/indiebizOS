#!/usr/bin/env python3
"""이벤트 루프 규율 정적 검사 — async 함수 본문의 동기 블로킹 호출 탐지.

왜: 백엔드가 단일 프로세스라 async 라우트 하나가 루프를 막으면 *서버 전체*가 선다.
게다가 이 서버는 자기 자신을 부르는 일이 잦아(창고 폴러→public_face→터널→자기,
폰↔맥 핑, /ibl/execute) 루프가 막힌 채 자기 요청을 기다리면 **자기교착**이 된다.
같은 부류가 세 번 재발했다(창고 폴러 add/poll · public_face 인프로세스 프록시 ·
/ibl/execute). 실행이 아니라 파싱으로 잡을 수 있는 부류라 AST 로 훑는다.

허용(플래그하지 않음) — ★이 세 가지가 이 검사의 정확도를 결정한다:
  - 중첩 sync 함수 / 람다 본문
      async 안에 def 를 두고 executor 에 넘기는 것이 *정석*이다. 이걸 구분 못 하는
      나이브 스캔은 backend/api_nodes.py 의 모범 사례를 오탐한다(2026-07-25 실측).
  - 중첩 class 의 sync 메서드
  - 줄 끝 또는 바로 윗줄의 `# eventloop-ok: <사유>` 주석
      진짜 예외는 사유와 함께 선언한다(부팅 1회성 등). 사유 없는 벌거벗은 억제는 불가.

고치는 법: `await asyncio.to_thread(fn, *args)` 또는
`await asyncio.get_running_loop().run_in_executor(None, fn)` 로 스레드에 내린다.
(FastAPI 라우트라면 `async def` 를 그냥 `def` 로 바꾸는 것도 답이다 — Starlette 이
sync 라우트를 알아서 스레드풀에서 돌린다.)

대상: backend/ + data/packages/installed/. async 함수가 없는 파일은 자연히 무관.
pre-commit 훅과 CI(seam-guards.yml) 양쪽에서 호출된다.
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SCAN_ROOTS = [ROOT / "backend", ROOT / "data" / "packages" / "installed"]
SKIP_DIRS = {"__pycache__", "_archive", "node_modules", ".git", "build", "dist"}

ALLOW_COMMENT = "eventloop-ok"

# 동기 블로킹 호출 — 점 표기 전체 이름으로 매칭한다(`import x` 든 함수 안 lazy
# import 든 호출부 모양은 같다). 보수적으로 "확실히 막는 것"만 넣는다:
# 파일 읽기·sqlite 처럼 짧고 편재하는 것은 넣지 않는다(오탐이 가드를 죽인다).
BLOCKING = {
    "time.sleep":                   "이벤트 루프 전체가 그 시간만큼 정지",
    "subprocess.run":               "자식 프로세스 종료까지 루프 정지",
    "subprocess.call":              "자식 프로세스 종료까지 루프 정지",
    "subprocess.check_call":        "자식 프로세스 종료까지 루프 정지",
    "subprocess.check_output":      "자식 프로세스 종료까지 루프 정지",
    "requests.get":                 "동기 HTTP — 자기 자신을 부르면 자기교착",
    "requests.post":                "동기 HTTP — 자기 자신을 부르면 자기교착",
    "requests.put":                 "동기 HTTP — 자기 자신을 부르면 자기교착",
    "requests.patch":               "동기 HTTP — 자기 자신을 부르면 자기교착",
    "requests.delete":              "동기 HTTP — 자기 자신을 부르면 자기교착",
    "requests.head":                "동기 HTTP — 자기 자신을 부르면 자기교착",
    "requests.request":             "동기 HTTP — 자기 자신을 부르면 자기교착",
    "urllib.request.urlopen":       "동기 HTTP",
    "socket.create_connection":     "동기 소켓 연결",
}

# `from time import sleep` 처럼 벌거벗은 이름으로 들어온 경우도 잡는다.
# {모듈: {심볼}} — 위 BLOCKING 에서 파생.
_FROM_TARGETS: dict[str, set[str]] = {}
for _dotted in BLOCKING:
    _mod, _, _sym = _dotted.rpartition(".")
    _FROM_TARGETS.setdefault(_mod, set()).add(_sym)


def _dotted_name(node: ast.AST) -> str | None:
    """ast.Attribute/Name 체인을 'a.b.c' 로 편다."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    return ".".join(reversed(parts))


def _bare_aliases(tree: ast.AST) -> dict[str, str]:
    """`from time import sleep` / `from subprocess import run as srun` →
    {로컬이름: 정식 점표기}. 모듈 어디에 있든(톱레벨·함수 안) 수집한다."""
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in _FROM_TARGETS:
            for alias in node.names:
                if alias.name in _FROM_TARGETS[node.module]:
                    out[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return out


def _allowed_lines(src: str) -> set[int]:
    """`# eventloop-ok: 사유` 가 달린 줄 + 그 바로 다음 줄(주석을 위에 단 경우)."""
    ok: set[int] = set()
    for i, line in enumerate(src.splitlines(), start=1):
        if ALLOW_COMMENT in line:
            ok.add(i)
            ok.add(i + 1)
    return ok


def _scan_async_body(node: ast.AST, bare: dict[str, str], out: list, fname: str):
    """async 함수 본문을 훑되, 중첩 sync 함수·람다·클래스 서브트리는 들어가지 않는다.
    (그것들은 루프에서 즉시 실행되지 않는다 — executor 에 넘기는 정석 패턴.)"""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.Lambda, ast.ClassDef)):
            # 중첩 sync 정의 — 여기서 멈춘다. 단 그 안의 async def 는 별도로 순회된다.
            for sub in ast.walk(child):
                if isinstance(sub, ast.AsyncFunctionDef):
                    _scan_async_body(sub, bare, out, sub.name)
            continue
        if isinstance(child, ast.AsyncFunctionDef):
            _scan_async_body(child, bare, out, child.name)
            continue
        if isinstance(child, ast.Call):
            name = _dotted_name(child.func)
            if name in bare:
                name = bare[name]
            if name in BLOCKING:
                out.append((child.lineno, name, BLOCKING[name], fname))
        _scan_async_body(child, bare, out, fname)


def scan_file(path: Path):
    try:
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as e:
        print(f"[warn] parse skip {path.relative_to(ROOT)}: {e.__class__.__name__}")
        return []
    bare = _bare_aliases(tree)
    ok_lines = _allowed_lines(src)
    out: list = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            _scan_async_body(node, bare, out, node.name)
    # 중복 제거(중첩 async 가 두 번 순회될 수 있음) + 억제 주석 반영
    seen = set()
    kept = []
    for lineno, name, why, fname in out:
        if lineno in ok_lines or (lineno, name) in seen:
            continue
        seen.add((lineno, name))
        kept.append((lineno, name, why, fname))
    return sorted(kept)


def main() -> int:
    flagged = []
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            for lineno, name, why, fname in scan_file(path):
                flagged.append((path.relative_to(ROOT), lineno, name, why, fname))

    if flagged:
        print(f"[FAIL] async 함수 본문의 동기 블로킹 호출 {len(flagged)}건 — 이벤트 루프가 멈춥니다:")
        for rel, lineno, name, why, fname in flagged:
            print(f"  {rel}:{lineno}  {name}()  in async {fname}()  — {why}")
        print()
        print("고치는 법:")
        print("  · await asyncio.to_thread(fn, *args)  (권장)")
        print("  · await asyncio.get_running_loop().run_in_executor(None, _nested_sync_fn)")
        print("  · FastAPI 라우트면 `async def` → `def` (Starlette 이 스레드풀로 돌림)")
        print("  · 진짜 예외면 그 줄에 `# eventloop-ok: <사유>` (사유 필수)")
        return 1

    print("[OK] 이벤트 루프 규율 통과 (async 본문에 동기 블로킹 호출 없음)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
