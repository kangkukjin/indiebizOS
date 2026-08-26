#!/usr/bin/env python3
"""사설 경로 워커 정적 검사 — 점 경로 해석의 방언 탄생을 커밋 전에 차단.

왜: "경로가 가리키는 값"의 워커가 5개 방언(블록 술어·응답 변환 추출/중첩·$변수
추출·flatten)으로 갈라져 같은 경로가 표면마다 다른 답을 냈다(2026-08-27 census
후 common/field_path.py 한 벌로 통일). 값 판정 관문(check_value_judgment)과 같은
교리 — 발견(상상훈련)을 기다리지 않고 탄생을 막는다.

무엇을 잡나 (AST): `X.split(".")` / `X.split('.')` 호출 — 점 경로를 손으로 쪼개는
전형. 경로 해석이면 common.field_path(parse_path/walk_path)로 위임하고, 경로가
아니면(호스트명·버전·문장 분리·클래스명) 그 줄에 `# path-ok: <사유>` 를 남긴다.
사유 없는 억제는 불가. BASELINE 동결 목록은 두지 않는다(silent_clamp 교리).

대상: backend/ + data/packages/installed/. pre-commit 에서 호출.
사용: 기본 = 관문 모드 · `--census` = 전수 보고.
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = [ROOT / "backend", ROOT / "data" / "packages" / "installed"]
SKIP_DIRS = {"__pycache__", "_archive", "node_modules", ".git", "build", "dist"}
OWNER_FILES = {"backend/common/field_path.py"}
ALLOW_COMMENT = "path-ok"


def _line_allowed(lines, lineno) -> bool:
    for idx in (lineno - 1, lineno - 2):
        if 0 <= idx < len(lines):
            text = lines[idx]
            if ALLOW_COMMENT in text:
                if text.split(ALLOW_COMMENT, 1)[1].lstrip(": ").strip():
                    return True
    return False


def _scan_file(path: Path, rel: str):
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "split" and len(node.args) == 1 \
                and isinstance(node.args[0], ast.Constant) and node.args[0].value == ".":
            if _line_allowed(lines, node.lineno):
                continue
            snippet = lines[node.lineno - 1].strip() if node.lineno - 1 < len(lines) else ""
            hits.append((rel, node.lineno, snippet[:110]))
    return hits


def main() -> int:
    census = "--census" in sys.argv
    all_hits = []
    for root in SCAN_ROOTS:
        for path in sorted(root.rglob("*.py")):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if path.name.startswith("test_") or path.name == "conftest.py":
                continue
            rel = str(path.relative_to(ROOT))
            if rel in OWNER_FILES:
                continue
            all_hits.extend(_scan_file(path, rel))
    if census:
        for rel, lineno, snippet in all_hits:
            print(f"{rel}:{lineno}  {snippet}")
        print(f"총 {len(all_hits)}자리")
        return 0
    if all_hits:
        print("[FAIL] 사설 경로 분해 — 점 경로 해석은 common/field_path 한 벌로:")
        for rel, lineno, snippet in all_hits:
            print(f"  {rel}:{lineno}\n      {snippet}")
        print("\n고치는 법: 경로 해석이면 common.field_path.walk_path/parse_path 위임, "
              f"경로가 아니면 그 줄에 `# {ALLOW_COMMENT}: <사유>` (사유 필수).")
        return 1
    print("✓ 사설 경로 분해 없음 — 경로 해석은 field_path 한 벌")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
