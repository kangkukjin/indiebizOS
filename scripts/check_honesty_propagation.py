#!/usr/bin/env python3
"""정직 표지 전파 관문 — 표지 목록을 **손으로 적는** 자리 탐지.

왜: 부분 실패·경로 변경의 *사실*을 나르는 봉투 키(정직 표지)의 정본은
`backend/ibl/ibl_honesty.py` 의 `HONESTY_KEYS` 한 벌이다. 그런데 조합 경계
(파이프·병렬·폴백·블록 몸·each·문장)는 저마다 "어떤 키를 위로 올릴까"를 **그 자리에서
손으로 열거**해 왔고, 열거에서 빠진 키는 그 경계에서 조용히 사라졌다. 같은 속의 결함이
다섯 번 반복됐다:

  · B24-1 (24회차) 병렬 — 가지 '전체 실패'만 신고, 가지 *안*의 부분 실패는 침묵
  · B27-4 (27회차) 블록 몸 — skipped_steps·condition_errors·_caught 셋만 건졌다
  · F35-1 (35회차) 폴백 — `_fallback_used` 가 최상위에 없어 첫 가지 결과로 착각됐다
  · B48-1 (48회차) try — catch 결과가 스칼라일 때 `_caught` 가 통째로 사라졌다
  · B48-2 (48회차) 병렬 — 가지가 살아 있으면 그 안의 부분 실패가 증발했다

다섯 번째에서 48회차 보고서가 밭 이관을 선언했다(가이드 §4-3): 부류가 기계로 열거
가능함이 반복 발견으로 실증됐으니, 여섯 번째 회차 대신 **탄생을 커밋 전에 차단**한다.
선례 = `check_value_judgment.py`(값 판정), `check_field_path.py`(경로 방언).

무엇을 잡나 (AST):
  [A] **손으로 적은 표지 목록** (전역) — list/tuple/set 리터럴 안에 표지 이름 문자열이
      2개 이상. 이것이 부류의 씨앗이다: 그 목록은 반드시 뒤처지고, 빠진 키는 그
      경계에서 침묵한다(위 다섯 사건 전부 이 모양이었다). `HONESTY_KEYS` 를 쓰거나,
      그 자리가 목록을 소유해야 할 사유를 남길 것.
  [B] **표지 배관이 없는 경계** — 아래 BOUNDARY_FILES 는 조합 경계를 소유하는 모듈이라
      표지를 걷거나 올리는 일이 직업이다. `ibl_honesty` 를 아예 참조하지 않으면
      그 경계는 표지를 나를 방법이 없다.
      ★BOUNDARY_FILES 는 사람이 관리하는 명단이다 — 새 조합 경계를 만들면 등록할 것.
        등록을 잊어도 규칙 [A]는 전역이라 손으로 적은 목록의 탄생은 잡힌다.

통과 조건(둘 중 하나):
  - `ibl_honesty` 의 HONESTY_KEYS / markers_of / merge_into 로 위임한다.
  - 그 줄 또는 바로 윗줄에 `# hp-ok: <사유>`. 사유 없는 억제는 불가.

BASELINE 동결 목록은 두지 않는다 — 파일당 숫자를 얼리면 사유가 어디에도 없다
(silent_clamp 가 2026-08-24 에 배운 것). 예외는 자리마다 hp-ok 사유로만.

대상: backend/ + data/packages/installed/ (시험 배터리는 부류상 표지 이름을 담는 자리라 제외).
사용: 기본 = 관문 모드(위반 시 exit 1) · `--census` = 전수 보고(분류 작업용).
"""
import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = [ROOT / "backend", ROOT / "data" / "packages" / "installed"]
SKIP_DIRS = {"__pycache__", "_archive", "node_modules", ".git", "build", "dist"}

ALLOW_COMMENT = "hp-ok"
OWNER_REL = "backend/ibl/ibl_honesty.py"      # 표지 목록의 주인 — 자기 자신은 대상 밖
OWNER_MODULE = "ibl_honesty"

#: **전파자** — 안쪽 봉투에서 표지를 걷어 바깥으로 올리는 일이 직업인 모듈(규칙 [B]).
#: ★생산자와 구별한다: `ibl_exec_each`(errors/error_count 를 *낳는다*)·
#:  `workflow_parallel`(가지를 돌릴 뿐, 걷기는 workflow_engine 의 `_seq` 가 한다)는
#:  자기 표지를 손으로 열거하지 않으므로 여기 없다 — 그 둘은 규칙 [A]가 지킨다.
#:  명단을 넓게 잡았다가 오탐이 나면 관문은 곧 무시당한다(첫 census 실측 3건이 그랬다).
BOUNDARY_FILES = {
    "backend/ibl/workflow_engine.py",       # 파이프 · 독립 문장 — 전 경계의 표지가 여기로 모인다
    "backend/ibl/ibl_control_blocks.py",    # [try] · [repeat:] — 회차·몸 경계에서 걷어 올린다
}


def _markers():
    sys.path.insert(0, str(ROOT / "backend"))
    sys.path.insert(0, str(ROOT / "backend" / "ibl"))
    from ibl_honesty import HONESTY_KEYS
    return set(HONESTY_KEYS)


def _iter_py():
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            if p.name.startswith("test_"):
                continue          # 가드 배터리는 표지 이름을 담는 것이 직업이다
            yield p


def _allowed(lines, lineno) -> bool:
    """그 줄 또는 바로 윗줄의 `# hp-ok: <사유>` — 사유 없는 억제는 불가."""
    for idx in (lineno - 1, lineno - 2):
        if 0 <= idx < len(lines):
            txt = lines[idx]
            if ALLOW_COMMENT in txt:
                after = txt.split(ALLOW_COMMENT, 1)[1].lstrip(": ").strip()
                if after:
                    return True
    return False


def scan(markers):
    hits = []
    for path in _iter_py():
        rel = path.relative_to(ROOT).as_posix()
        if rel == OWNER_REL:
            continue
        try:
            src = path.read_text(encoding="utf-8")
            tree = ast.parse(src)
        except (SyntaxError, UnicodeDecodeError):
            continue
        lines = src.splitlines()
        delegates = OWNER_MODULE in src

        # [A] 손으로 적은 표지 목록
        for node in ast.walk(tree):
            if not isinstance(node, (ast.List, ast.Tuple, ast.Set)):
                continue
            names = [e.value for e in node.elts
                     if isinstance(e, ast.Constant) and isinstance(e.value, str)]
            found = sorted(set(names) & markers)
            if len(found) >= 2 and not _allowed(lines, node.lineno):
                hits.append((rel, node.lineno, "A",
                             f"손으로 적은 표지 목록 {found} — HONESTY_KEYS 를 쓰거나 hp-ok 사유를 남기세요"))

        # [B] 표지 배관이 없는 경계
        if rel in BOUNDARY_FILES and not delegates:
            hits.append((rel, 1, "B",
                         "조합 경계인데 ibl_honesty 를 참조하지 않습니다 — 이 경계는 표지를 나를 수 없습니다"))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--census", action="store_true", help="전수 보고(관문 모드 아님)")
    args = ap.parse_args()

    markers = _markers()
    hits = scan(markers)

    if args.census:
        print(f"[honesty_propagation] 표지 {len(markers)}종 · 경계 {len(BOUNDARY_FILES)}곳 · 히트 {len(hits)}건")
        for rel, line, rule, msg in sorted(hits):
            print(f"  [{rule}] {rel}:{line} {msg}")
        return 0

    if hits:
        print("✗ 정직 표지 전파 관문 위반", file=sys.stderr)
        for rel, line, rule, msg in sorted(hits):
            print(f"  [{rule}] {rel}:{line} {msg}", file=sys.stderr)
        print("\n표지 목록의 정본은 backend/ibl/ibl_honesty.py 의 HONESTY_KEYS 하나입니다.",
              file=sys.stderr)
        print("손으로 적은 목록은 반드시 뒤처지고, 빠진 키는 그 경계에서 조용히 사라집니다",
              file=sys.stderr)
        print("(B24-1 · B27-4 · F35-1 · B48-1 · B48-2 — 같은 속으로 다섯 번).", file=sys.stderr)
        return 1

    print(f"✓ 정직 표지 전파 OK — 표지 {len(markers)}종, 경계 {len(BOUNDARY_FILES)}곳 전부 위임")
    return 0


if __name__ == "__main__":
    sys.exit(main())
