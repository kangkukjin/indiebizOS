#!/usr/bin/env python3
"""동시성 규율 정적 검사 — 기계로 판정 가능한 동시성 위험 부류의 탄생 차단.

왜: 동시성 밭의 기록된 부류(싱글턴 로더 레이스→load_singleton 정본화 · 워커 스레드
리로드 사멸 · 리로드 유령 워커 · episode logger→contextvar)는 각각 수리됐지만,
새 자리의 탄생을 막는 관문이 없었다(2026-08-27 census: connect 107·Thread 63).
값 판정·경로 관문과 같은 교리 — 판정 가능한 부류만 정직하게 가드한다.

무엇을 잡나 (AST):
  [A] `sqlite3.connect(...)` 에 명시 `timeout=` 없음 — 다중 프로세스(backend 워커·
      스케줄러·외부 스크립트·keeper)가 같은 DB 를 쓰는 몸에서 잠금 대기의 선언은
      저자의 결정이어야 한다(기본 5s 암묵 의존 금지). 하우스 정본 = `timeout=10`.
  [B] `threading.Thread(...)` 생성이 **data/packages/installed/** 안에 있음 —
      패키지 코드는 리로드되는 워커에서 돌므로 백그라운드 스레드가 조용히 죽는
      위험지대다(pitfall: worker-thread-dies-on-reload — 긴 작업은 별도 프로세스+
      pid 하트비트). join 으로 수명을 봉인했거나 다음 호출이 재무장하는 설계면
      그 사유를 그 자리에 남긴다.
  [C] `check_same_thread=False` — 커넥션의 크로스스레드 공유는 잠금 설계가 있어야
      한다. 사유 의무.

통과 조건: 그 줄 또는 바로 윗줄의 `# cc-ok: <사유>` (사유 필수 — 동결 목록 금지,
silent_clamp 교리). [A] 는 timeout= 명시로도 통과.

★관문 밖(수용된 잔여 — 정직 기록): backend/ 의 엔진 스레드(50자리)는 프로세스와
함께 재기동되는 수명이라 부류가 다르고, "긴 작업인가"는 기계로 판정 불능이다 —
그 규율은 pitfall 원장(worker-thread-dies-on-reload)이 소유한다. 락 없는 공유
가변 상태·사설 지연 싱글턴도 AST 로 판정 불능(정본은 common/pkg_utils.load_singleton).

대상: backend/ + data/packages/installed/. pre-commit 에서 호출.
사용: 기본 = 관문 모드 · `--census` = 전수 보고.
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = [ROOT / "backend", ROOT / "data" / "packages" / "installed"]
SKIP_DIRS = {"__pycache__", "_archive", "node_modules", ".git", "build", "dist"}
ALLOW_COMMENT = "cc-ok"
PACKAGES_PREFIX = "data/packages/installed/"


def _line_allowed(lines, lineno) -> bool:
    for idx in (lineno - 1, lineno - 2):
        if 0 <= idx < len(lines):
            text = lines[idx]
            if ALLOW_COMMENT in text:
                if text.split(ALLOW_COMMENT, 1)[1].lstrip(": ").strip():
                    return True
    return False


def _is_call_to(node, module: str, attr: str) -> bool:
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == attr and isinstance(node.func.value, ast.Name)
            and node.func.value.id == module)


def _scan_file(path: Path, rel: str):
    src = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    lines = src.splitlines()
    hits = []

    def report(node, rule, what):
        if _line_allowed(lines, node.lineno):
            return
        snippet = lines[node.lineno - 1].strip() if node.lineno - 1 < len(lines) else ""
        hits.append((rel, node.lineno, rule, what, snippet[:110]))

    in_packages = rel.startswith(PACKAGES_PREFIX)
    for node in ast.walk(tree):
        if _is_call_to(node, "sqlite3", "connect"):
            kwargs = {kw.arg for kw in node.keywords}
            if "timeout" not in kwargs:
                report(node, "A", "sqlite3.connect 에 timeout= 명시 없음 — 잠금 대기는 저자의 결정(하우스 정본 timeout=10)")
            if "check_same_thread" in kwargs:
                for kw in node.keywords:
                    if kw.arg == "check_same_thread" and isinstance(kw.value, ast.Constant) \
                            and kw.value.value is False:
                        report(node, "C", "check_same_thread=False — 크로스스레드 공유는 잠금 설계 사유 의무")
        if in_packages and _is_call_to(node, "threading", "Thread"):
            report(node, "B", "패키지(리로드 워커) 안 Thread — 리로드 사멸 위험지대: 수명 설계 사유 의무")
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
            all_hits.extend(_scan_file(path, str(path.relative_to(ROOT))))
    if census:
        cur = None
        for rel, lineno, rule, what, snippet in all_hits:
            if rel != cur:
                print(f"\n── {rel}")
                cur = rel
            print(f"  {lineno:>5} [{rule}] {snippet}")
        print(f"\n총 {len(all_hits)}자리 · 파일 {len({h[0] for h in all_hits})}개")
        return 0
    if all_hits:
        print("[FAIL] 동시성 규율 — 잠금 대기·워커 스레드 수명은 선언돼야 한다:")
        for rel, lineno, rule, what, snippet in all_hits[:40]:
            print(f"  {rel}:{lineno} [{rule}] {what}\n      {snippet}")
        if len(all_hits) > 40:
            print(f"  … 외 {len(all_hits) - 40}자리")
        print(f"\n고치는 법: [A] timeout=10 명시 · [B]/[C] 수명·잠금 설계를 그 줄에 "
              f"`# {ALLOW_COMMENT}: <사유>` 로 (사유 필수).")
        return 1
    print("✓ 동시성 규율 통과 — 잠금 대기·워커 스레드 수명 전부 선언됨")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
